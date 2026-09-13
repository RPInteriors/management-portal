from pathlib import Path
import re, shutil, subprocess

p=Path('index.html'); s=p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
shutil.copy2(p,Path('backups')/f'index-before-credential-safety-v2-{sha}.html')

s,n=re.subn(r'(?ms)^      async function completeForgotPasswordReset\(\) \{.*?^      \}\n\n      async function resetUserPassword\(\)', '''      async function completeForgotPasswordReset() {
        alert("This recovery path is disabled for security. Use the authenticated credential-change flow.");
      }

      async function resetUserPassword()''', s, count=1)
if n!=1: raise SystemExit('forgot recovery replacement failed')

s,n=re.subn(r'(?ms)^      async function resetUserPasswordWithoutOldPassword\(\) \{.*?^      \}\n\n      function ', '''      async function resetUserPasswordWithoutOldPassword() {
        alert("This recovery path is disabled for security. Use the authenticated credential-change flow.");
      }

      function ''', s, count=1)
if n!=1: raise SystemExit('no-credential recovery replacement failed')

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','data.userProfiles','userProfiles: USER_PROFILES']:
    if bad in s: raise SystemExit('insecure pattern remains')
if s.count('This recovery path is disabled for security.') < 2: raise SystemExit('recovery safety text missing')
p.write_text(s,encoding='utf-8'); print('CREDENTIAL SAFETY V2 PASSED')
