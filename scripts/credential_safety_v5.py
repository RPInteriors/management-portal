from pathlib import Path
import shutil, subprocess

p=Path('index.html'); s=p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
shutil.copy2(p,Path('backups')/f'index-before-credential-safety-v5-{sha}.html')

a=s.find('async function completeForgotPasswordReset()')
b=s.find('async function resetUserPassword()',a)
if a<0 or b<0: raise SystemExit('first recovery markers missing')
line_start=s.rfind('\n',0,a)+1
s=s[:line_start]+'      async function completeForgotPasswordReset() {\n        alert("This recovery path is disabled for security. Use the authenticated credential-change flow.");\n      }\n\n'+s[b-6:]

a=s.find('async function resetUserPasswordWithoutOldPassword()')
b=s.find('function ',a+10)
if a<0 or b<0: raise SystemExit('second recovery markers missing')
line_start=s.rfind('\n',0,a)+1
s=s[:line_start]+'      async function resetUserPasswordWithoutOldPassword() {\n        alert("This recovery path is disabled for security. Use the authenticated credential-change flow.");\n      }\n\n'+s[b-6:]

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','data.userProfiles','userProfiles: USER_PROFILES']:
    if bad in s: raise SystemExit('insecure pattern remains')
p.write_text(s,encoding='utf-8');print('CREDENTIAL SAFETY V5 PASSED')
