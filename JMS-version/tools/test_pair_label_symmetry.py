from pathlib import Path
import unittest,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'joint_model'))
from validate import validate
from model import Config
from joint_pairing_model import products_from_load_ports
from pair_label_symmetry import canonical_seed


class LabelTests(unittest.TestCase):
    def test_four_actual_witnesses_preserve_physical_routes(self):
        base=Path(__file__).resolve().parents[1]/'results/optimality_work_20261021'
        names=('manuscript_warm_n16_H3_4x1','manuscript_warm_n16_H10_4x1_transfer',
               'manuscript_warm_n16_H3_2x2_v2','manuscript_warm_n16_H10_2x2_v2')
        for name in names:
            original=json.loads((base/name/'result.json').read_text(encoding='utf-8-sig'))
            products=products_from_load_ports(Config(**original['config']).load_ports)
            new,mapping=canonical_seed(original,[w.identifier for w in products])
            replay=validate(new)
            self.assertTrue(replay['valid'],(name,replay['errors']))
            self.assertEqual(replay['product_return_cmax'],validate(original)['product_return_cmax'])
            self.assertEqual(sorted((e['start'],e['end'],e['location']) for e in original['events']),
                             sorted((e['start'],e['end'],e['location']) for e in new['events']))
            again,_=canonical_seed(new,[w.identifier for w in products])
            self.assertEqual(new['pairs'],again['pairs'])


if __name__=='__main__':unittest.main()
