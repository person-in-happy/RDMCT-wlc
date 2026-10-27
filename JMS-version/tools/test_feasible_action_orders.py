import copy,unittest
from export_feasible_action_orders import make_config,template,construct,audit_projection,actions,permutation_at


class ActionOrderTests(unittest.TestCase):
    def fixture(self,recipe='4x1',h=3,rank=0):
        cfg=make_config(8,recipe,h);ids=[f'LP{lp}_W{w}' for lp in range(1,5) for w in (1,2)]
        return construct(cfg,template(permutation_at(ids,rank),recipe,h,1,'early'))

    def test_all_products_and_two_exposures(self):
        data=self.fixture('2x2');audit=audit_projection(data)
        self.assertTrue(audit['physical']['valid'])
        self.assertEqual(sum(j['product'] for j in data['jobs']),8)
        self.assertEqual(audit['physical']['processing_cycles'],16)
        self.assertEqual(audit['physical']['cleaning_count'],8)

    def test_numeric_translation_does_not_create_new_order(self):
        data=self.fixture();translated=copy.deepcopy(data)
        for item in translated['events']+translated['cycles']:
            item['start']+=7;item['end']+=7
        self.assertEqual(actions(data)[1],actions(translated)[1])

    def test_distinct_product_order_and_same_h_physics(self):
        a=self.fixture();b=self.fixture(rank=40319);c=self.fixture(h=10)
        self.assertTrue(audit_projection(b)['physical']['valid'])
        self.assertNotEqual(actions(a)[1],actions(b)[1])
        self.assertEqual(actions(a)[1],actions(c)[1])

    def test_overlap_is_not_serialized(self):
        data=self.fixture();changed=copy.deepcopy(data)
        changed['events'][1]['start']=changed['events'][0]['start']
        changed['events'][1]['end']=changed['events'][0]['end']
        self.assertNotEqual(actions(data)[1],actions(changed)[1])
        with self.assertRaises(ValueError):audit_projection(changed)


if __name__=='__main__':unittest.main()
