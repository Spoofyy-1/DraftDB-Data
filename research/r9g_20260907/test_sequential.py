"""Fail-closed completion and frozen registry fixtures; no models."""
import copy,unittest
import sequential_launch as S
class Gate(unittest.TestCase):
 def setUp(self):
  self.s={'status':'completed','completed':435,'matched_summary':{'reference_replays_passed':3,'interpretation_allowed':True,'completed_tasks':435},'saved_blends':{'all_endpoints_and_roundtrips_exact':True}}
  self.c={'status':'completed','tasks':435,'saved_blends_complete':True};self.u={'ActiveState':'inactive','Result':'success','ExecMainStatus':'0'}
 def test_requires_success(self):
  self.assertTrue(S.gate(self.s,self.c,self.u))
  for field,value in [('Result','timeout'),('ExecMainStatus','1'),('ActiveState','failed')]:
   u={**self.u,field:value}
   with self.assertRaises(AssertionError):S.gate(self.s,self.c,u)
 def test_waits_while_F_process_alive(self):self.assertFalse(S.gate(self.s,self.c,{**self.u,'ActiveState':'active'}))
 def test_rejects_missing_references_or_partial_blends(self):
  for x in [0,2]:
   s=copy.deepcopy(self.s);s['matched_summary']['reference_replays_passed']=x
   with self.assertRaises(AssertionError):S.gate(s,self.c,self.u)
  with self.assertRaises(AssertionError):S.gate(self.s,{**self.c,'saved_blends_complete':False},self.u)
 def test_requires_all_tasks(self):
  with self.assertRaises(AssertionError):S.gate({**self.s,'completed':434},self.c,self.u)
 def test_error_never_launches(self):
  with self.assertRaises(AssertionError):S.gate({**self.s,'error':'failure'},self.c,self.u)
if __name__=='__main__':unittest.main()
