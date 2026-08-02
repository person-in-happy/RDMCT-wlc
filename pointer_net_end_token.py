import torch
import torch.nn as nn
import torch.autograd as autograd
from torch.autograd import Variable
from torch.nn.parameter import Parameter
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint
from torch.distributions import Normal
import math
import numpy as np

from scip_imports import SCIP_RESULT, scip

from beam_search import (
    Beam,
    gather_beam_embeddings,
    probabilities_to_log_probs,
    reorder_beam_tensor,
)
from utils import cut_feature_generator
from logger import logger
from pointer_net import Encoder, StructureAwareInputAdapter

LOG_STD_MAX = 2
LOG_STD_MIN = -20

# from ipdb import set_trace
# from ipdb import set_trace 

class Attention(nn.Module):
    """A generic attention module for a decoder in seq2seq"""
    def __init__(self, dim, use_tanh=False, C=10, use_cuda=True):
        super(Attention, self).__init__()
        self.use_tanh = use_tanh
        self.project_query = nn.Linear(dim, dim)
        self.project_ref = nn.Conv1d(dim, dim, 1, 1)
        self.C = C  # tanh exploration
        self.tanh = nn.Tanh()
        
        # v = torch.FloatTensor(dim)
        # if use_cuda:
        #     v = v.cuda()  
        self.v = nn.Parameter(torch.FloatTensor(dim))
        self.v.data.uniform_(-(1. / math.sqrt(dim)) , 1. / math.sqrt(dim))
        
    def encode_ref(self, ref):
        ref = ref.permute(1, 2, 0)
        return self.project_ref(ref)

    def score(self, query, encoded_ref):
        q = self.project_query(query).unsqueeze(2)  # batch x dim x 1
        # batch x 1 x hidden_dim
        v_view = self.v.unsqueeze(0).expand(
                q.size(0), len(self.v)).unsqueeze(1)
        # [batch_size x 1 x hidden_dim] * [batch_size x hidden_dim x sourceL]
        u = torch.bmm(v_view, self.tanh(q + encoded_ref)).squeeze(1)
        if self.use_tanh:
            logits = self.C * self.tanh(u)
        else:
            logits = u
        return logits

    def forward(self, query, ref):
        """
        Args: 
            query: is the hidden state of the decoder at the current
                time step. batch x dim
            ref: the set of hidden states from the encoder. 
                sourceL x batch x hidden_dim
        """
        if ref.dim() == 3 and ref.size(0) == query.size(0):
            e = ref
            if query.requires_grad:
                logits = checkpoint(self.score, query, e, use_reentrant=False)
            else:
                logits = self.score(query, e)
        else:
            e = self.encode_ref(ref)
            logits = self.score(query, e)
        return e, logits

class DecoderEndToken(nn.Module):
    def __init__(self, 
            embedding_dim,
            hidden_dim,
            tanh_exploration,
            use_tanh,
            n_glimpses=1,
            beam_size=0,
            use_cuda=True):
        super(DecoderEndToken, self).__init__()
        
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.n_glimpses = n_glimpses
        self.beam_size = beam_size
        self.use_cuda = use_cuda

        self.input_weights = nn.Linear(embedding_dim, 4 * hidden_dim)
        self.hidden_weights = nn.Linear(hidden_dim, 4 * hidden_dim)

        self.pointer = Attention(hidden_dim, use_tanh=use_tanh, C=tanh_exploration, use_cuda=self.use_cuda)
        self.glimpse = Attention(hidden_dim, use_tanh=False, use_cuda=self.use_cuda)
        self.sm = nn.Softmax(dim=1)

    def apply_mask_to_logits(self, step, logits, mask, prev_idxs):    
        if mask is None:
            mask = torch.zeros(logits.size(), dtype=torch.bool, device=self.pointer.v.device)
            # if self.use_cuda:
            #     mask = mask.cuda()
    
        maskk = mask.clone()

        # to prevent them from being reselected. 
        # Or, allow re-selection and penalize in the objective function
        if prev_idxs is not None:
            # set most recently selected idx values to 1
            maskk[[x for x in range(logits.size(0))],
                    prev_idxs.data] = True
            logits[maskk] = -np.inf
        return logits, maskk

    def _attention_logits(self, attention_module, query, encoded_ref, use_checkpoint):
        if use_checkpoint and query.requires_grad:
            return checkpoint(attention_module.score, query, encoded_ref, use_reentrant=False)
        return attention_module.score(query, encoded_ref)

    def logprobs(self, decoder_input, embedded_inputs, hidden, context, max_length, seled_idxes, collect_pointer_probs=False):
        glimpse_ref = self.glimpse.encode_ref(context)
        pointer_ref = self.pointer.encode_ref(context)

        def recurrence(x, hidden, logit_mask, prev_idxs, step):
            
            hx, cx = hidden  # batch_size x hidden_dim
            
            gates = self.input_weights(x) + self.hidden_weights(hx)
            ingate, forgetgate, cellgate, outgate = gates.chunk(4, 1)

            ingate = F.sigmoid(ingate)
            forgetgate = F.sigmoid(forgetgate)
            cellgate = F.tanh(cellgate)
            outgate = F.sigmoid(outgate)

            cy = (forgetgate * cx) + (ingate * cellgate)
            hy = outgate * F.tanh(cy)  # batch_size x hidden_dim
            
            g_l = hy
            for i in range(self.n_glimpses):
                ref, logits = self.glimpse(g_l, glimpse_ref)
                logits, logit_mask = self.apply_mask_to_logits(step, logits, logit_mask, prev_idxs)
                # [batch_size x h_dim x sourceL] * [batch_size x sourceL x 1] = 
                # [batch_size x h_dim x 1]
                g_l = torch.bmm(ref, self.sm(logits).unsqueeze(2)).squeeze(2) 
            _, logits = self.pointer(g_l, context) # logits 代表基于context vector 的概率分布
            
            logits, logit_mask = self.apply_mask_to_logits(step, logits, logit_mask, prev_idxs)
            log_probs = F.log_softmax(logits, dim=1)
            probs = log_probs.exp()
            return hy, cy, probs, log_probs, logit_mask
    
        batch_size = context.size(1)
        context = pointer_ref
        outputs = [] if collect_pointer_probs else None
        logprob = torch.zeros((batch_size, 1), device=self.pointer.v.device)
        steps = range(max_length)  # or until terminating symbol ?
        idxs = None
        mask = None
       
        for i in steps:
            hx, cx, probs, log_probs, mask = recurrence(decoder_input, hidden, mask, idxs, i)
            hidden = (hx, cx)
            # select the next inputs for the decoder [batch_size x hidden_dim]
            selected_idx = int(seled_idxes[i])
            decoder_input = self.decode_logp(
                embedded_inputs,
                seled_idxes[i]) # 每一次decode 都是随机sample 一个输出
            idxs = torch.tensor([selected_idx], dtype=torch.int64).to(self.pointer.v.device)
            # if self.use_cuda:
            #     idxs = idxs.cuda()
            # use outs to point to next object
            logprob = logprob + log_probs[:, selected_idx:selected_idx+1]
            if collect_pointer_probs:
                outputs.append(probs.detach().cpu())

        return (outputs, logprob), hidden

    def decode_logp(self, embedded_inputs, idxs):
        batch_size = embedded_inputs.size(1)
        # due to race conditions, might need to resample here
        sels = embedded_inputs[idxs, [i for i in range(batch_size)], :] 
        return sels

    def forward(self, decoder_input, embedded_inputs, hidden, context, max_length, decode_type):
        """
        Args:
            decoder_input: The initial input to the decoder
                size is [batch_size x embedding_dim]. Trainable parameter.
            embedded_inputs: [sourceL x batch_size x embedding_dim]
            hidden: the prev hidden state, size is [batch_size x hidden_dim]. 
                Initially this is set to (enc_h[-1], enc_c[-1])
            context: encoder outputs, [sourceL x batch_size x hidden_dim] 
        """
        def recurrence(x, hidden, logit_mask, prev_idxs, step):
            
            hx, cx = hidden  # batch_size x hidden_dim
            
            gates = self.input_weights(x) + self.hidden_weights(hx)
            ingate, forgetgate, cellgate, outgate = gates.chunk(4, 1)

            ingate = F.sigmoid(ingate)
            forgetgate = F.sigmoid(forgetgate)
            cellgate = F.tanh(cellgate)
            outgate = F.sigmoid(outgate)

            cy = (forgetgate * cx) + (ingate * cellgate)
            hy = outgate * F.tanh(cy)  # batch_size x hidden_dim
            
            g_l = hy
            for i in range(self.n_glimpses):
                ref, logits = self.glimpse(g_l, context)
                logits, logit_mask = self.apply_mask_to_logits(step, logits, logit_mask, prev_idxs)
                # [batch_size x h_dim x sourceL] * [batch_size x sourceL x 1] = 
                # [batch_size x h_dim x 1]
                g_l = torch.bmm(ref, self.sm(logits).unsqueeze(2)).squeeze(2) 
            _, logits = self.pointer(g_l, context) # logits 代表基于context vector 的概率分布
            
            logits, logit_mask = self.apply_mask_to_logits(step, logits, logit_mask, prev_idxs)
            probs = self.sm(logits)
            return hy, cy, probs, logit_mask
    
        batch_size = context.size(1)
        end_token_idx = embedded_inputs.size(0) - 1
        outputs = []
        selections = []
        steps = range(max_length)  # or until terminating symbol ?
        inps = []
        idxs = None
        mask = None
       
        if decode_type in ["stochastic", "greedy"]:
            for i in steps:
                hx, cx, probs, mask = recurrence(decoder_input, hidden, mask, idxs, i)
                hidden = (hx, cx)
                selection_probs = probs
                if i == max_length - 1:
                    selection_probs = torch.zeros_like(probs)
                    selection_probs[:, end_token_idx] = 1.0
                # select the next inputs for the decoder [batch_size x hidden_dim]
                decoder_input, idxs = self.decode(
                    selection_probs,
                    embedded_inputs,
                    selections,
                    decode_type) # 每一次decode 都是随机sample 一个输出
                inps.append(decoder_input) 
                # use outs to point to next object
                outputs.append(probs)
                selections.append(idxs)

                if idxs.numel() == 1 and int(idxs.reshape(-1)[0].item()) == end_token_idx:
                    # Stop only when the actual appended end token is selected.
                    break
            return (outputs, selections), hidden
        
        elif decode_type == "beam_search":
            if batch_size != 1:
                raise ValueError(
                    "end-token beam decoding currently requires batch_size == 1"
                )
            beam_size = max(1, min(int(self.beam_size), int(embedded_inputs.size(0))))
            decoder_input = decoder_input.repeat(beam_size, 1)
            context = context.repeat(1, beam_size, 1)
            hidden = (
                hidden[0].repeat(beam_size, 1),
                hidden[1].repeat(beam_size, 1),
            )
            beams = [
                Beam(
                    beam_size,
                    max_length,
                    device=decoder_input.device,
                    dtype=decoder_input.dtype,
                    eos_idx=end_token_idx,
                )
                for _ in range(batch_size)
            ]
            probability_history = []

            for i in steps:
                hx, cx, probs, mask = recurrence(decoder_input, hidden, mask, idxs, i)
                probs_by_batch = (
                    probs.reshape(beam_size, batch_size, -1)
                    .transpose(0, 1)
                    .contiguous()
                )
                log_probs_by_batch = probabilities_to_log_probs(probs_by_batch)
                force_eos = i == max_length - 1
                for batch_idx in range(batch_size):
                    beams[batch_idx].advance(
                        log_probs_by_batch[batch_idx],
                        force_eos=force_eos,
                    )

                parent_rows = torch.stack(
                    [item.get_current_origin() for item in beams],
                    dim=0,
                )
                token_rows = torch.stack(
                    [item.get_current_state() for item in beams],
                    dim=0,
                )
                hidden = (
                    reorder_beam_tensor(hx, parent_rows),
                    reorder_beam_tensor(cx, parent_rows),
                )
                mask = reorder_beam_tensor(mask, parent_rows)
                idxs = token_rows.transpose(0, 1).contiguous().reshape(-1)
                decoder_input = gather_beam_embeddings(embedded_inputs, token_rows)
                probability_history.append(probs_by_batch)
                if all(item.done for item in beams):
                    break

            best = [item.get_best_hypothesis(prefer_finished=True) for item in beams]
            decoded_steps = len(best[0][0])
            selections = [
                torch.stack([best[b][0][step] for b in range(batch_size)])
                for step in range(decoded_steps)
            ]
            outputs = [
                torch.stack(
                    [
                        probability_history[step][b, best[b][1][step], :]
                        for b in range(batch_size)
                    ],
                    dim=0,
                )
                for step in range(decoded_steps)
            ]
            final_rows = torch.tensor(
                [item[2] for item in best],
                dtype=torch.long,
                device=decoder_input.device,
            )
            final_hidden = (
                hidden[0].index_select(0, final_rows),
                hidden[1].index_select(0, final_rows),
            )
            return (outputs, selections), final_hidden

        else:
            raise NotImplementedError

    def decode(self, probs, embedded_inputs, selections, decode_type):
        """
        Return the next input for the decoder by selecting the 
        input with sampling

        Args: 
            probs: [batch_size x sourceL]
            embedded_inputs: [sourceL x batch_size x embedding_dim]
            selections: list of all of the previously selected indices during decoding
       Returns:
            Tensor of size [batch_size x sourceL] containing the embeddings
            from the inputs corresponding to the [batch_size] indices
            selected for this iteration of the decoding, as well as the 
            corresponding indicies
        """
        batch_size = probs.size(0)
        # idxs is [batch_size]
        if decode_type == "stochastic":
            idxs = probs.multinomial(num_samples=1).squeeze(1)
        elif decode_type == "greedy":
            max_probs, idxs = probs.max(1)
        assert idxs not in set(selections)

        sels = embedded_inputs[idxs.data, [i for i in range(batch_size)], :] 
        return sels, idxs


class PointerNetworkEndToken(nn.Module):
    """The pointer network, which is the core seq2seq 
    model"""
    def __init__(self, 
            embedding_dim,
            hidden_dim,
            n_glimpses,
            tanh_exploration, # tanh exploration coefficient
            use_tanh,
            beam_size,
            use_cuda):
        super(PointerNetworkEndToken, self).__init__()

        self.embedding_dim = embedding_dim
        self.input_adapter = StructureAwareInputAdapter(embedding_dim)
        self.encoder = Encoder(
                embedding_dim,
                hidden_dim,
                use_cuda)

        self.decoder = DecoderEndToken(
                embedding_dim,
                hidden_dim,
                tanh_exploration=tanh_exploration,
                use_tanh=use_tanh,
                n_glimpses=n_glimpses,
                beam_size=beam_size,
                use_cuda=use_cuda)

        # Trainable initial hidden states
        # dec_in_0 = torch.FloatTensor(embedding_dim)
        # if use_cuda:
        #     dec_in_0 = dec_in_0.cuda()

        self.decoder_in_0 = nn.Parameter(torch.FloatTensor(embedding_dim))
        self.decoder_in_0.data.uniform_(-(1. / math.sqrt(embedding_dim)),
                1. / math.sqrt(embedding_dim))
            
    def forward(self, inputs, max_decode_len, decode_type):
        """ Propagate inputs through the network
        Args: 
            inputs: [sourceL x batch_size x embedding_dim]
        """
        inputs = self.input_adapter(inputs)
        # preprocess inputs 
        end_token = torch.ones((1,inputs.shape[1],inputs.shape[2]),dtype=torch.float,device=inputs.device)
        inputs = torch.cat((inputs, end_token), axis=0)

        (encoder_hx, encoder_cx) = self.encoder.enc_init_state
        encoder_hx = encoder_hx.unsqueeze(0).repeat(inputs.size(1), 1).unsqueeze(0)       
        encoder_cx = encoder_cx.unsqueeze(0).repeat(inputs.size(1), 1).unsqueeze(0)       
        
        # encoder forward pass
        enc_h, (enc_h_t, enc_c_t) = self.encoder(inputs, (encoder_hx, encoder_cx))

        dec_init_state = (enc_h_t[-1], enc_c_t[-1])
    
        # repeat decoder_in_0 across batch
        decoder_input = self.decoder_in_0.unsqueeze(0).repeat(inputs.size(1), 1)
        (pointer_probs, input_idxs), dec_hidden_t = self.decoder(decoder_input,
                inputs,
                dec_init_state,
                enc_h,
                max_decode_len,
                decode_type)

        return pointer_probs, input_idxs

    def _prob_to_logp(self, prob):
        logprob = 0
        for p in prob:
            logp = torch.log(p)
            logprob += logp
        # logprob[(logprob < -10000).detach()] = 0.
        
        return logprob

    def logprobs(self, inputs, max_decode_len, seled_idxes, return_pointer_probs=False):
        """ Propagate inputs through the network
        Args: 
            inputs: [sourceL x batch_size x embedding_dim]
        """
        inputs = self.input_adapter(inputs)
        # preprocess inputs 
        end_token = torch.ones((1,inputs.shape[1],inputs.shape[2]),dtype=torch.float,device=inputs.device)
        inputs = torch.cat((inputs, end_token), axis=0)

        (encoder_hx, encoder_cx) = self.encoder.enc_init_state
        encoder_hx = encoder_hx.unsqueeze(0).repeat(inputs.size(1), 1).unsqueeze(0)       
        encoder_cx = encoder_cx.unsqueeze(0).repeat(inputs.size(1), 1).unsqueeze(0)       
        
        # encoder forward pass
        enc_h, (enc_h_t, enc_c_t) = self.encoder(inputs, (encoder_hx, encoder_cx))

        dec_init_state = (enc_h_t[-1], enc_c_t[-1])
    
        # repeat decoder_in_0 across batch
        decoder_input = self.decoder_in_0.unsqueeze(0).repeat(inputs.size(1), 1)

        (pointer_probs, logprob), dec_hidden_t = self.decoder.logprobs(decoder_input,
                inputs,
                dec_init_state,
                enc_h,
                max_decode_len,
                seled_idxes,
                collect_pointer_probs=return_pointer_probs)
        
        return pointer_probs, logprob


    
# test 
if __name__ == "__main__":
    import time
    embedding_dim = 13
    hidden_dim = 128
    max_decoding_len = 100
    decode_type = 'greedy'
    n_glimpses = 2
    tanh_exploration = 10
    use_tanh = True
    use_cuda = True
    beam_size = 1

    ptr_net = PointerNetworkEndToken(
        embedding_dim=embedding_dim,
        hidden_dim=hidden_dim,
        n_glimpses=n_glimpses,
        tanh_exploration=tanh_exploration,
        use_tanh=use_tanh,
        beam_size=beam_size,
        use_cuda=use_cuda
    ).to('cuda:0')

    # (seq_len, batch_size, feature_dim)
    input_x = torch.randn((max_decoding_len, 1, 13)).to('cuda:0')
    for _ in range(5):
        st = time.time()
        pointer_probs, input_idxs = ptr_net(input_x, max_decoding_len+1, decode_type)
        et = time.time() - st
        _, logp = ptr_net.logprobs(input_x, len(input_idxs), input_idxs)
        print(f"time: {et}")
        print(f"selected_idxs: {len(input_idxs)}")
