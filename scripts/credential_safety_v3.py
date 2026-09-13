from pathlib import Path
import re, shutil, subprocess

p=Path('index.html'); s=p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
shutil.copy2(p,Path('backups')/f'index-before-credential-safety-v3-{sha}.html')

pattern=r'(?s)function\s+completeForgotPasswordReset\s*\(\s*\)\s*\{.*?\}\s*function\s+resetUserPassword\s*\(\s*\)'
s,n=re.subn(pattern,'async function completeForgotPasswordReset() { alert("This recovery path is disabled for security. Use the authenticated credential-change flow."); }\n\n      async function resetUserPassword()',s,count=1)
if n!=1: raise SystemExit('first recovery function not found')
pattern=r'(?s)function\s+resetUserPasswordWithoutOldPassword\s*\(\s*\)\s*\{.*?\}\s*function\s+'
s,n=re.subn(pattern,'async function resetUserPasswordWithoutOldPassword() { alert("This recovery path is disabled for security. Use the authenticated credential-change flow."); }\n\n      function ',s,count=1)
if n!=1: raise SystemExit('second recovery function not found')

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','data.userProfiles','userProfiles: USER_PROFILES']:
    if bad in s: raise SystemExit('insecure pattern remains')
p.write_text(s,encoding='utf-8');print('CREDENTIAL SAFETY V3 PASSED')
