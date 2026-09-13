from pathlib import Path
import shutil, subprocess

p=Path('index.html'); s=p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
shutil.copy2(p,Path('backups')/f'index-before-credential-safety-{sha}.html')

def replace_region(src,start,end,repl):
    a=src.find(start); b=src.find(end,a+len(start))
    if a<0 or b<0: raise SystemExit('required markers missing')
    return src[:a]+repl+src[b:]

s=replace_region(s,'      async function completeForgotPasswordReset() {','      async function resetUserPassword()', '''      async function completeForgotPasswordReset() {
        alert("This recovery path is disabled for security. Use the authenticated credential-change flow.");
      }

''')
s=replace_region(s,'      async function resetUserPasswordWithoutOldPassword() {','      function ', '''      async function resetUserPasswordWithoutOldPassword() {
        alert("This recovery path is disabled for security. Use the authenticated credential-change flow.");
      }

''')

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','data.userProfiles','userProfiles: USER_PROFILES']:
    if bad in s: raise SystemExit('insecure pattern remains')
p.write_text(s,encoding='utf-8')
print('CREDENTIAL SAFETY PASSED')
