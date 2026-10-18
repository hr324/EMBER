"""Tests for the prospective fire-spread GNN extension."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HAS_TORCH = importlib.util.find_spec('torch') is not None


@unittest.skipUnless(HAS_TORCH, 'Optional PyTorch is not installed')
class TestGNNForecast(unittest.TestCase):
    """Verify temporal isolation and genuine neural-network gradients."""

    @classmethod
    def setUpClass(cls):
        """Load the standalone training script without installing project packages."""
        import sys
        sys.path.insert(0,str(ROOT/'scripts'))
        sys.path.insert(0,str(ROOT/'src'))
        import gnn_forecast
        cls.f = gnn_forecast
        cls.observations=gnn_forecast.load_firms(ROOT/'data/synthetic/toy_firms.csv')
        cls.passes=gnn_forecast.get_passes(cls.observations)

    def test_future_observations_do_not_change_input_graph(self):
        """A future pass may define labels but must never enter model inputs."""
        before=self.f.build_example('toy',self.passes[:1],None,[],cell_m=1500,
                                    margin_km=7,max_cells=1000)
        labelled=self.f.build_example('toy',self.passes[:1],self.passes[1],[],cell_m=1500,
                                      margin_km=7,max_cells=1000)
        self.assertTrue(self.f.torch.equal(before.x,labelled.x))
        self.assertTrue(self.f.torch.equal(before.edge_features,labelled.edge_features))
        self.assertIsNone(before.label)
        self.assertGreater(int(labelled.label.sum()),0)

    def test_trainable_gnn_receives_gradient(self):
        """GNN computes nonzero gradients for its learned message-passing parameters."""
        case=self.f.build_example('toy',self.passes[:1],self.passes[1],[],cell_m=1500,
                                  margin_km=7,max_cells=1000)
        model=self.f.EdgeAwareGNN(hidden=16)
        logits=model(case)
        self.assertEqual(logits.shape[0],len(case.grid.nodes))
        self.f.balanced_loss(logits,case.label).backward()
        grad=sum(float(p.grad.abs().sum()) for p in model.parameters() if p.grad is not None)
        self.assertGreater(grad,0)


if __name__=='__main__':unittest.main()
