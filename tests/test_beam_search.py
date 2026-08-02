import math

import pytest

torch = pytest.importorskip("torch")

from beam_search import (
    Beam,
    gather_beam_embeddings,
    probabilities_to_log_probs,
    reorder_beam_tensor,
)


def test_beam_accumulates_joint_log_probability():
    beam = Beam(size=2, steps=2, device="cpu")
    # Two already-live prefixes. Adding raw probabilities would prefer
    # 0.99 + 0.20 over 0.58 + 0.58, while joint likelihood prefers the
    # second parent: 0.58 * 0.58 > 0.99 * 0.20.
    beam.scores = torch.log(torch.tensor([0.99, 0.58]))
    next_probs = torch.tensor([[0.20, 0.01], [0.58, 0.01]])
    beam.advance(probabilities_to_log_probs(next_probs))

    assert int(beam.get_current_origin()[0].item()) == 1
    assert float(beam.scores[0].exp().item()) == pytest.approx(0.58 * 0.58)


def test_get_best_uses_rank_zero_for_beam_size_one():
    beam = Beam(size=1, steps=1, device="cpu")
    beam.advance(probabilities_to_log_probs(torch.tensor([[0.7, 0.3]])))
    score, row = beam.get_best()

    assert int(row.item()) == 0
    assert float(score.exp().item()) == pytest.approx(0.7)


def test_parent_rows_reorder_hidden_mask_and_embeddings():
    # Beam-major rows are (k0,b0), (k0,b1), (k1,b0), (k1,b1),
    # (k2,b0), (k2,b1). New parents are listed batch-by-beam.
    tensor = torch.arange(12).reshape(6, 2)
    parent_rows = torch.tensor([[2, 0, 1], [1, 2, 0]])
    reordered = reorder_beam_tensor(tensor, parent_rows)
    expected_order = torch.tensor([4, 3, 0, 5, 2, 1])
    assert torch.equal(reordered, tensor.index_select(0, expected_order))

    embedded = torch.arange(5 * 2 * 3).reshape(5, 2, 3)
    token_rows = torch.tensor([[4, 1, 3], [0, 2, 4]])
    gathered = gather_beam_embeddings(embedded, token_rows)
    assert torch.equal(gathered[0], embedded[4, 0])
    assert torch.equal(gathered[1], embedded[0, 1])
    assert torch.equal(gathered[2], embedded[1, 0])
    assert torch.equal(gathered[3], embedded[2, 1])


def test_eos_hypothesis_is_archived_and_score_is_frozen():
    eos = 1
    beam = Beam(size=2, steps=3, device="cpu", eos_idx=eos)
    beam.advance(
        probabilities_to_log_probs(
            torch.tensor([[0.60, 0.40], [0.01, 0.01]])
        )
    )
    assert not beam.done

    beam.advance(
        probabilities_to_log_probs(
            torch.tensor([[0.10, 0.05], [0.50, 0.50]])
        )
    )
    tokens, _, _, score = beam.get_best_hypothesis(prefer_finished=True)

    assert beam.done
    assert [int(token.item()) for token in tokens] == [eos]
    assert math.exp(float(score.item())) == pytest.approx(0.40)
