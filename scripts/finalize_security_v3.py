from pathlib import Path
import re, shutil, subprocess

p=Path('index.html'); s=p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
shutil.copy2(p,Path('backups')/f'index-before-final-security-v3-{sha}.html')

def region(src,start,end,repl,label):
    a=src.find(start); b=src.find(end,a+len(start))
    if a<0 or b<0: raise SystemExit(label+' markers missing')
    return src[:a]+repl+src[b:]

s=re.sub(r'      const DEFAULT_USER_PROFILES = \{.*?      \};','''      const DEFAULT_USER_PROFILES = {\n        CEO: "", Administrator: "", Supervisor: "",\n      };''',s,count=1,flags=re.S)

storage='''      // --- STORAGE LOGIC ---
      function readEmployeeLocalBackup() { try { const raw=localStorage.getItem("RPI_employee_backup"); const parsed=raw?JSON.parse(raw):[]; return Array.isArray(parsed)&&parsed.length>0?sortEmployeesById(parsed):[]; } catch(error){ console.warn("RPI employee backup read failed:",error); return []; } }
      function writeEmployeeLocalBackup(employeeList) { if(!Array.isArray(employeeList)||employeeList.length===0)return; try{const safeList=sortEmployeesById(employeeList);localStorage.setItem("RPI_employee_backup",JSON.stringify(safeList));localStorage.setItem("RPI_employee_backup_time",new Date().toISOString());}catch(error){console.warn("RPI local employee backup failed:",error);} }
      function saveToLocalStorage() { let safeEmployees=Array.isArray(employees)?sortEmployeesById(employees):[]; const backupEmployees=readEmployeeLocalBackup(); if(safeEmployees.length===0&&backupEmployees.length>0){safeEmployees=backupEmployees;employees=safeEmployees;} const updates={projects,expenseRecords,materialRecords}; if(safeEmployees.length>0){employees=safeEmployees;updates.employees=safeEmployees;writeEmployeeLocalBackup(safeEmployees);}else console.warn("RPI protection: BLOCKED an empty employee overwrite. Employee data was not changed in Firebase."); return database.ref("portalData").update(updates).catch(error=>{console.error("Cloud Sync Error:",error);throw error;}); }

'''
s=region(s,'      // --- STORAGE LOGIC ---','      function initUserProfilesSync() {',storage,'storage')
s=region(s,'      function initUserProfilesSync() {','      async function applyForcedCodePasswords()', '      function initUserProfilesSync() { USER_PROFILES={...DEFAULT_USER_PROFILES}; }\n\n','user sync')
s=region(s,'      async function applyForcedCodePasswords() {','      function ', '      async function applyForcedCodePasswords() { throw new Error("Legacy code-password recovery is disabled."); }\n\n','legacy recovery')

a=s.find('      async function ensureForceSyncAuthSession() {'); b=s.find('      async function syncRolePasswordToFirebaseAuth(',a)
if a>=0 and b>=0:s=s[:a]+'      async function ensureForceSyncAuthSession() { if(!auth.currentUser)return null; currentUserRole=getCurrentSignedInRole(); return currentUserRole; }\n\n'+s[b:]

# Main authentication: replace the existing client-side password comparison with Firebase Auth.
s=s.replace('if (USER_PROFILES[role] === pass)', 'if (await verifyRolePasswordInFirebaseAuth(role, pass))', 1)
# The existing function must be async for the await above.
s=s.replace('function handleGlobalLogin()', 'async function handleGlobalLogin()', 1)
# Remove any legacy profile cleanup/read/write from the login flow.
if 'await database.ref("portalData/userProfiles").remove()' not in s:
    marker='          initApplication();'
    s=s.replace(marker,'          await database.ref("portalData/userProfiles").remove().catch(error => console.warn("Legacy password cleanup failed:", error));\n'+marker,1)

# Administrator secondary gate: convert function and replace plaintext comparison only.
s=s.replace('function login() {','async function login() {',1)
s=s.replace('if (pass === USER_PROFILES["Administrator"])','if (await verifyRolePasswordInFirebaseAuth("Administrator", pass))',1)

# Cloud sync ignores legacy password table.
s=region(s,'      function initCloudSync() {','      // --- AUTH LOGIC ---','''      function initCloudSync() {
        const employeeRef=database.ref("portalData/employees");
        employeeRef.on("value",snapshot=>{const cloudEmployees=snapshot.val();if(Array.isArray(cloudEmployees)&&cloudEmployees.length>0){employees=sortEmployeesById(cloudEmployees);writeEmployeeLocalBackup(employees);}else{const backupEmployees=readEmployeeLocalBackup();if(backupEmployees.length>0){employees=backupEmployees;employeeRef.set(employees).catch(error=>console.error("RPI employee recovery write failed:",error));}else console.warn("RPI protection: no employee backup available; refusing empty overwrite.");}const activePage=Array.from(document.querySelectorAll(".page")).find(page=>page.style.display==="block")?.id;if(activePage==="page1")renderEmployeeList();if(activePage==="page4")renderAdminPanel();});
        database.ref("portalData").on("value",snapshot=>{const data=snapshot.val();if(!data)return;projects=data.projects||[];expenseRecords=data.expenseRecords||[];materialRecords=data.materialRecords||[];normalizeProjectsData();const activePage=Array.from(document.querySelectorAll(".page")).find(page=>page.style.display==="block")?.id;if(activePage==="page1")renderEmployeeList();if(activePage==="pageExpense")renderExpenses();if(activePage==="pageMaterials")renderMaterials();if(activePage==="page3")renderProjectDashboard();if(activePage==="page4")renderAdminPanel();});
      }

''','cloud sync')

# Old-password change flow verifies against Firebase Auth.
s=s.replace('if (USER_PROFILES[role] !== oldPassword)', 'if (!(await verifyRolePasswordInFirebaseAuth(role, oldPassword)))')
s=re.sub(r'          USER_PROFILES\[role\] = password;\n          await database\.ref\("portalData/userProfiles"\)\.set\(USER_PROFILES\);','          await syncRolePasswordToFirebaseAuth(role, oldPassword, password);',s)

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','userProfiles: USER_PROFILES','data.userProfiles','presetPassword = DEFAULT_USER_PROFILES']:
    if bad in s: raise SystemExit('Forbidden insecure pattern: '+bad)
for marker in ['function readEmployeeLocalBackup()','function writeEmployeeLocalBackup(employeeList)','BLOCKED an empty employee overwrite','database.ref("portalData/employees")','verifyRolePasswordInFirebaseAuth(role, pass)','verifyRolePasswordInFirebaseAuth("Administrator", pass)']:
    if marker not in s: raise SystemExit('Missing verification marker: '+marker)
for name in ['readEmployeeLocalBackup','writeEmployeeLocalBackup','saveToLocalStorage','initCloudSync']:
    if len(re.findall(r'function '+name+r'\s*\(',s))!=1: raise SystemExit('Duplicate/missing function: '+name)
p.write_text(s,encoding='utf-8');print('FINAL SECURITY V3 PASSED')
