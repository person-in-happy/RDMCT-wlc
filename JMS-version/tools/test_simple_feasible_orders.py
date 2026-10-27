import copy,gzip,json,unittest
from export_simple_feasible_orders import ROOT,abstract_handling,certify_substitution,substitute,render,product_order


class SimpleOrdersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'JMS-version/gif/kexingyu/evidence/8wafer-witnesses.jsonl.gz'
        with gzip.open(path,'rt',encoding='utf-8') as stream:cls.data=json.loads(next(stream))['witness']

    def test_handling_only_with_complete_coverage(self):
        groups=abstract_handling(self.data);text=render(groups,product_order(self.data))
        self.assertEqual(sum(map(len,groups)),sum(e['robot'] in ('ATR','VTR') for e in self.data['events']))
        for word in ('START','END','PROCESS','CLEAN','rotate'):self.assertNotIn(word,text)
        for w in product_order(self.data):self.assertIn(w.replace('_W','.')+' ATR取 ',text)

    def test_relabeling_replays_and_projects_exactly(self):
        proof=certify_substitution(self.data);self.assertGreaterEqual(proof['minimum_cross_product_lp_gap'],3)
        order=list(reversed(product_order(self.data)));new=substitute(self.data,order)
        self.assertTrue(new['validation']['valid'])
        self.assertEqual(render(abstract_handling(self.data),order),render(abstract_handling(new),order))
        self.assertNotEqual(render(abstract_handling(self.data),order),render(abstract_handling(self.data),product_order(self.data)))

    def test_no_bijection_is_rejected(self):
        ids=product_order(self.data);ids[-1]=ids[0]
        with self.assertRaisesRegex(ValueError,'bijection'):substitute(self.data,ids)

    def test_same_start_is_grouped(self):
        data=copy.deepcopy(self.data);events=[e for e in data['events'] if e['robot'] in ('ATR','VTR')]
        events[1]['start']=events[0]['start']
        self.assertEqual(len(abstract_handling(data)[0]),2)
        self.assertIn(' || ',render(abstract_handling(data),product_order(data)))


if __name__=='__main__':unittest.main()
