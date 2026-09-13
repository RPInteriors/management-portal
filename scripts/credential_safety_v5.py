from pathlib import Path
import shutil, subprocess, re

p = Path('index.html')
s = p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha = subprocess.check_output(['git','rev-parse','--short','HEAD'], text=True).strip()
shutil.copy2(p, Path('backups') / f'index-before-credential-safety-v5-{sha}.html')

def disable_function(source, name):
    pattern = re.compile(r'(?m)^(\s*)async function ' + re.escape(name) + r'\s*\([^)]*\)\s*\{')
    m = pattern.search(source)
    if not m:
        raise SystemExit(f'{name} marker missing')
    start = m.start()
    brace = source.find('{', m.start())
    depth = 0
    i = brace
    while i < len(source):
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    else:
        raise SystemExit(f'{name} closing brace missing')
    indent = m.group(1)
    replacement = (f'{indent}async function {name}() {{\n'
                   f'{indent}  alert("This recovery path is disabled for security. Use the authenticated credential-change flow.");\n'
                   f'{indent}}}')
    return source[:start] + replacement + source[end:]

s = disable_function(s, 'completeForgotPasswordReset')
s = disable_function(s, 'resetUserPasswordWithoutOldPassword')

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','data.userProfiles','userProfiles: USER_PROFILES']:
    if bad in s:
        raise SystemExit(f'insecure pattern remains: {bad}')

p.write_text(s, encoding='utf-8')
print('CREDENTIAL SAFETY V5 PASSED')
