# beam search implementation in PyTorch."""
#
#
#         hyp1#-hyp1---hyp1 -hyp1
#                 \             /
#         hyp2 \-hyp2 /-hyp2#hyp2
#                               /      \
#         hyp3#-hyp3---hyp3 -hyp3
#         ========================
#
# Takes care of beams, back pointers, and scores.

# Code borrowed from https://github.com/MaximumEntropy/Seq2Seq-PyTorch/blob/master/beam_search.py,
# who borrowed it from PyTorch OpenNMT example
# https://github.com/pytorch/examples/blob/master/OpenNMT/onmt/Beam.py
# :-) 

import torch


class Beam(object):
    """Ordered beam scored by joint log-probability."""

    def __init__(
        self,
        size,
        steps,
        cuda=False,
        device=None,
        dtype=torch.float32,
        eos_idx=None,
    ):
        """Initialize a beam; only its first row is live at step zero."""
        if int(size) <= 0:
            raise ValueError("beam size must be positive")
        if int(steps) <= 0:
            raise ValueError("beam steps must be positive")
        self.size = int(size)
        self.done = False
        self.pad = -1
        self.steps = int(steps)
        self.current_step = 0
        self.device = (
            torch.device(device)
            if device is not None
            else torch.device("cuda" if cuda else "cpu")
        )
        self.eos_idx = None if eos_idx is None else int(eos_idx)

        self.scores = torch.full(
            (self.size,),
            -torch.inf,
            dtype=dtype,
            device=self.device,
        )
        self.scores[0] = 0.0
        self.finished = torch.zeros(
            self.size,
            dtype=torch.bool,
            device=self.device,
        )
        self.finished_hypotheses = []

        self.prevKs = []
        self.nextYs = [
            torch.full(
                (self.size,),
                self.pad,
                dtype=torch.long,
                device=self.device,
            )
        ]
        self.attn = []

    # Get the outputs for the current timestep.
    def get_current_state(self):
        """Get state of beam."""
        return self.nextYs[-1]

    # Get the backpointers for the current timestep.
    def get_current_origin(self):
        """Get the backpointer to the beam at this step."""
        return self.prevKs[-1]

    #  Given prob over words for every last beam `wordLk` and attention
    #   `attnOut`: Compute and update the beam search.
    #
    # Parameters:
    #
    #     * `wordLk`- probs of advancing from the last step (K x words)
    #     * `attnOut`- attention at the last step
    #
    # Returns: True if beam search is complete.

    def advance(self, word_log_probs, force_eos=False):
        """Advance from a beam-by-token matrix of log-probabilities."""
        if word_log_probs.dim() != 2 or word_log_probs.size(0) != self.size:
            raise ValueError(
                "word_log_probs must have shape [beam_size, vocabulary_size]"
            )
        if word_log_probs.device != self.device:
            raise ValueError(
                f"beam is on {self.device}, probabilities are on {word_log_probs.device}"
            )
        num_words = int(word_log_probs.size(1))
        if self.eos_idx is not None and not 0 <= self.eos_idx < num_words:
            raise ValueError("eos_idx is outside the beam vocabulary")
        if force_eos and self.eos_idx is None:
            raise ValueError("force_eos requires eos_idx")

        beam_lk = word_log_probs + self.scores.unsqueeze(1)
        if force_eos:
            forced = torch.full_like(beam_lk, -torch.inf)
            forced[:, self.eos_idx] = beam_lk[:, self.eos_idx]
            beam_lk = forced

        # Completed rows use a zero-cost EOS self-loop. Short sequences keep
        # their score and never acquire tokens after the first EOS.
        if self.eos_idx is not None and bool(self.finished.any()):
            beam_lk = beam_lk.clone()
            beam_lk[self.finished] = -torch.inf
            beam_lk[self.finished, self.eos_idx] = self.scores[self.finished]

        flat_beam_lk = beam_lk.reshape(-1)
        best_scores, best_ids = flat_beam_lk.topk(
            self.size,
            dim=0,
            largest=True,
            sorted=True,
        )
        prev_k = torch.div(best_ids, num_words, rounding_mode="floor")
        next_y = best_ids - prev_k * num_words
        parent_finished = self.finished.index_select(0, prev_k)

        self.prevKs.append(prev_k)
        self.nextYs.append(next_y)
        self.scores = best_scores
        self.current_step += 1

        if self.eos_idx is not None:
            newly_finished = (~parent_finished) & next_y.eq(self.eos_idx)
            self.finished = parent_finished | next_y.eq(self.eos_idx)
            for beam_row in torch.nonzero(newly_finished, as_tuple=False).reshape(-1):
                row = int(beam_row.item())
                self.finished_hypotheses.append(
                    (self.scores[row].detach().clone(), self.current_step, row)
                )

        self.done = self.current_step >= self.steps
        if self.eos_idx is not None:
            self.done = self.done or bool(self.finished.all())
            if self.finished_hypotheses:
                best_finished = max(
                    float(item[0].item())
                    for item in self.finished_hypotheses
                )
                live_scores = self.scores[~self.finished]
                if live_scores.numel() == 0 or best_finished >= float(live_scores.max().item()):
                    self.done = True

        return self.done

    def sort_best(self):
        """Sort the beam."""
        return torch.sort(self.scores, 0, True)

    # Get the score of the best in the beam.
    def get_best(self):
        """Get the most likely candidate."""
        scores, ids = self.sort_best()
        return scores[0], ids[0]

    # Walk back to construct the full hypothesis.
    #
    # Parameters.
    #
    #     * `k` - the position in the beam to construct.
    #
    # Returns.
    #
    #     1. The hypothesis
    #     2. The attention at each time step.
    def get_hyp(self, k, num_steps=None):
        """Backtrack one hypothesis, optionally from an archived step."""
        num_steps = len(self.prevKs) if num_steps is None else int(num_steps)
        if not 0 <= num_steps <= len(self.prevKs):
            raise ValueError("num_steps is outside the decoded history")
        k = int(k.item()) if torch.is_tensor(k) else int(k)
        hyp = []
        for j in range(num_steps - 1, -1, -1):
            hyp.append(self.nextYs[j + 1][k])
            k = int(self.prevKs[j][k].item())
        return hyp[::-1]

    def get_hyp_with_parents(self, k, num_steps=None):
        """Return tokens and the parent row that emitted each token."""
        num_steps = len(self.prevKs) if num_steps is None else int(num_steps)
        k = int(k.item()) if torch.is_tensor(k) else int(k)
        tokens = []
        parents = []
        for j in range(num_steps - 1, -1, -1):
            tokens.append(self.nextYs[j + 1][k])
            parent = int(self.prevKs[j][k].item())
            parents.append(parent)
            k = parent
        return tokens[::-1], parents[::-1]

    def get_best_hypothesis(self, prefer_finished=True):
        """Return tokens, emitting parents, final row, and score."""
        if prefer_finished and self.finished_hypotheses:
            score, num_steps, row = max(
                self.finished_hypotheses,
                key=lambda item: float(item[0].item()),
            )
        else:
            score, row_tensor = self.get_best()
            num_steps = len(self.prevKs)
            row = int(row_tensor.item())
        tokens, parents = self.get_hyp_with_parents(row, num_steps=num_steps)
        if self.eos_idx is not None:
            for position, token in enumerate(tokens):
                if int(token.item()) == self.eos_idx:
                    tokens = tokens[: position + 1]
                    parents = parents[: position + 1]
                    break
        return tokens, parents, row, score


def reorder_beam_tensor(tensor, parent_rows):
    """Reorder a beam-major tensor by a batch-by-beam parent matrix."""
    if parent_rows.dim() != 2:
        raise ValueError("parent_rows must have shape [batch_size, beam_size]")
    batch_size, beam_size = parent_rows.shape
    if tensor.size(0) != batch_size * beam_size:
        raise ValueError("tensor leading dimension does not match batch_size * beam_size")
    batch_offsets = torch.arange(
        batch_size,
        device=parent_rows.device,
        dtype=parent_rows.dtype,
    ).unsqueeze(1)
    flat_order = (parent_rows * batch_size + batch_offsets).transpose(0, 1).reshape(-1)
    return tensor.index_select(0, flat_order)


def gather_beam_embeddings(embedded_inputs, token_rows):
    """Gather one next-token embedding for every batch-by-beam row."""
    if token_rows.dim() != 2:
        raise ValueError("token_rows must have shape [batch_size, beam_size]")
    batch_size, beam_size = token_rows.shape
    if embedded_inputs.size(1) != batch_size:
        raise ValueError("embedded_inputs batch dimension does not match token_rows")
    batch_ids = torch.arange(
        batch_size,
        device=token_rows.device,
        dtype=torch.long,
    ).repeat(beam_size)
    flat_tokens = token_rows.transpose(0, 1).contiguous().reshape(-1)
    return embedded_inputs[flat_tokens, batch_ids, :]


def probabilities_to_log_probs(probabilities):
    """Take logs while preserving masked zero probabilities as negative infinity."""
    log_probs = torch.full_like(probabilities, -torch.inf)
    positive = probabilities > 0
    log_probs[positive] = probabilities[positive].log()
    return log_probs
