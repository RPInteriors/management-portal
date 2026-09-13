from pathlib import Path
import re, shutil, subprocess

p=Path('index.html'); s=p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
shutil.copy2(p,Path('backups')/f'index-before-credential-safety-v4-{sha}.html')

p1=r'(?s)(?:async\s+)?function\s+completeForgotPasswordReset\s*\(\s*\)\s*\{.*?(?=\n\s*(?:async\s+)?function\s+resetUserPassword\s*\()'
s,n=re.subn(p1,'async function completeForgotPasswordReset() { alert("This recovery path is disabled for security. Use the authenticated credential-change flow."); }\n\n      ',s,count=1)
if n!=1: raise SystemExit('first recovery function not found')

p2=r'(?s)(?:async\s+)?function\s+resetUserPasswordWithoutOldPassword\s*\(\s*\)\s*\{.*?(?=\n\s*function\s+)'
s,n=re.subn(p2,'async function resetUserPasswordWithoutOldPassword() { alert("This recovery path is disabled for security. Use the authenticated credential-change flow."); }\n\n      ',s,count=1)
if n!=1: raise SystemExit('second recovery function not found')

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','data.userProfiles','userProfiles: USER_PROFILES']:
    if bad in s: raise SystemExit('insecure pattern remains')
if s.count('This recovery path is disabled for security.')<2: raise SystemExit('recovery safety missing')
p.write_text(s,encoding='utf-8');print('CREDENTIAL SAFETY V4 PASSED')
