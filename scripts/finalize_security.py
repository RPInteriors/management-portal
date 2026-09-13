from pathlib import Path
import re, shutil, subprocess

p=Path('index.html'); s=p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha=subprocess.check_output(['git','rev-parse','--short','HEAD'],text=True).strip()
shutil.copy2(p,Path('backups')/f'index-before-final-security-{sha}.html')

def region(src,start,end,repl,label):
    a=src.find(start); b=src.find(end,a+len(start))
    if a<0 or b<0: raise SystemExit(label+' markers missing')
    return src[:a]+repl+src[b:]

s=re.sub(r'      const DEFAULT_USER_PROFILES = \{.*?      \};','''      const DEFAULT_USER_PROFILES = {\n        CEO: "", Administrator: "", Supervisor: "",\n      };''',s,count=1,flags=re.S)

storage='''      // --- STORAGE LOGIC ---
      function readEmployeeLocalBackup() {
        try { const raw=localStorage.getItem("RPI_employee_backup"); const parsed=raw?JSON.parse(raw):[]; return Array.isArray(parsed)&&parsed.length>0?sortEmployeesById(parsed):[]; }
        catch(error){ console.warn("RPI employee backup read failed:",error); return []; }
      }
      function writeEmployeeLocalBackup(employeeList) {
        if(!Array.isArray(employeeList)||employeeList.length===0)return;
        try{const safeList=sortEmployeesById(employeeList);localStorage.setItem("RPI_employee_backup",JSON.stringify(safeList));localStorage.setItem("RPI_employee_backup_time",new Date().toISOString());}
        catch(error){console.warn("RPI local employee backup failed:",error);}
      }
      function saveToLocalStorage() {
        let safeEmployees=Array.isArray(employees)?sortEmployeesById(employees):[]; const backupEmployees=readEmployeeLocalBackup();
        if(safeEmployees.length===0&&backupEmployees.length>0){safeEmployees=backupEmployees;employees=safeEmployees;}
        const updates={projects,expenseRecords,materialRecords};
        if(safeEmployees.length>0){employees=safeEmployees;updates.employees=safeEmployees;writeEmployeeLocalBackup(safeEmployees);}
        else console.warn("RPI protection: BLOCKED an empty employee overwrite. Employee data was not changed in Firebase.");
        return database.ref("portalData").update(updates).catch(error=>{console.error("Cloud Sync Error:",error);throw error;});
      }

'''
s=region(s,'      // --- STORAGE LOGIC ---','      function initUserProfilesSync() {',storage,'storage')

s=region(s,'      function initUserProfilesSync() {','      async function applyForcedCodePasswords()', '''      function initUserProfilesSync() {
        USER_PROFILES={...DEFAULT_USER_PROFILES};
      }

''','user sync')
s=region(s,'      async function applyForcedCodePasswords() {','      function ','''      async function applyForcedCodePasswords() {
        throw new Error("Legacy code-password recovery is disabled.");
      }

''','legacy recovery')

a=s.find('      async function ensureForceSyncAuthSession() {'); b=s.find('      async function syncRolePasswordToFirebaseAuth(',a)
if a>=0 and b>=0:s=s[:a]+'''      async function ensureForceSyncAuthSession() {
        if(!auth.currentUser)return null;
        currentUserRole=getCurrentSignedInRole(); return currentUserRole;
      }

'''+s[b:]

# Global login: use simple markers, not fragile regex.
a=s.find('      function handleGlobalLogin() {'); b=s.find('      function closeLogin()',a)
if a<0: a=s.find('      async function handleGlobalLogin() {')
if a<0 or b<0: raise SystemExit('global login markers missing')
login='''      async function handleGlobalLogin() {
        const role=document.getElementById("userRole").value; const pass=document.getElementById("globalPassword").value.trim(); const errorMsg=document.getElementById("loginError");
        if(!role||!pass){errorMsg.textContent="Please choose a role and enter password.";errorMsg.style.display="block";return;}
        const email=getRoleEmail(role); if(!email){errorMsg.textContent="Role is not configured for Firebase Authentication.";errorMsg.style.display="block";return;}
        try{const credential=await auth.signInWithEmailAndPassword(email,pass);currentUserRole=getCurrentSignedInRole();if(!credential.user||currentUserRole!==role){await auth.signOut();throw new Error("Role mismatch");}await database.ref("portalData/userProfiles").remove().catch(error=>console.warn("Legacy password cleanup failed:",error));sessionStorage.setItem("rp_auth_role",role);document.getElementById("globalPassword").value="";errorMsg.style.display="none";initApplication();}
        catch(error){console.error("Firebase authentication failed:",error);errorMsg.textContent="Invalid credentials or authentication unavailable.";errorMsg.style.display="block";}
      }

'''
s=s[:a]+login+s[b:]

# Administrator secondary gate.
a=s.find('      function login() {');
if a<0:a=s.find('      async function login() {')
b=s.find('      function closeLogin()',a)
if a<0 or b<0:raise SystemExit('admin login markers missing')
admin='''      async function login() {
        const pass=document.getElementById("adminPassword").value.trim();
        if(currentUserRole!=="Administrator"){alert("Access Denied: Administrator profile required!");return;}
        try{if(!(await verifyRolePasswordInFirebaseAuth("Administrator",pass)))throw new Error("Invalid administrator credentials");document.getElementById("loginOverlay").style.display="none";document.getElementById("adminPassword").value="";showPage("page4");}
        catch(error){console.error("Administrator verification failed:",error);alert("Access Denied: Administrator profile required!");}
      }

'''
s=s[:a]+admin+s[b:]

sync='''      function initCloudSync() {
        const employeeRef=database.ref("portalData/employees");
        employeeRef.on("value",snapshot=>{const cloudEmployees=snapshot.val();if(Array.isArray(cloudEmployees)&&cloudEmployees.length>0){employees=sortEmployeesById(cloudEmployees);writeEmployeeLocalBackup(employees);}else{const backupEmployees=readEmployeeLocalBackup();if(backupEmployees.length>0){employees=backupEmployees;employeeRef.set(employees).catch(error=>console.error("RPI employee recovery write failed:",error));}else console.warn("RPI protection: no employee backup available; refusing empty overwrite.");}const activePage=Array.from(document.querySelectorAll(".page")).find(page=>page.style.display==="block")?.id;if(activePage==="page1")renderEmployeeList();if(activePage==="page4")renderAdminPanel();});
        database.ref("portalData").on("value",snapshot=>{const data=snapshot.val();if(!data)return;projects=data.projects||[];expenseRecords=data.expenseRecords||[];materialRecords=data.materialRecords||[];normalizeProjectsData();const activePage=Array.from(document.querySelectorAll(".page")).find(page=>page.style.display==="block")?.id;if(activePage==="page1")renderEmployeeList();if(activePage==="pageExpense")renderExpenses();if(activePage==="pageMaterials")renderMaterials();if(activePage==="page3")renderProjectDashboard();if(activePage==="page4")renderAdminPanel();});
      }

'''
s=region(s,'      function initCloudSync() {','      // --- AUTH LOGIC ---',sync,'cloud sync')

s=s.replace('        if (USER_PROFILES[role] !== oldPassword) {\n          alert("Old password is incorrect.");\n          return;\n        }','        if (!(await verifyRolePasswordInFirebaseAuth(role, oldPassword))) {\n          alert("Old password is incorrect.");\n          return;\n        }')
s=re.sub(r'          USER_PROFILES\[role\] = password;\n          await database\.ref\("portalData/userProfiles"\)\.set\(USER_PROFILES\);','          await syncRolePasswordToFirebaseAuth(role, oldPassword, password);',s)

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','userProfiles: USER_PROFILES','data.userProfiles','presetPassword = DEFAULT_USER_PROFILES']:
    if bad in s: raise SystemExit('Forbidden insecure pattern: '+bad)
for marker in ['function readEmployeeLocalBackup()','function writeEmployeeLocalBackup(employeeList)','BLOCKED an empty employee overwrite','database.ref("portalData/employees")','auth.signInWithEmailAndPassword(email,pass)','verifyRolePasswordInFirebaseAuth("Administrator",pass)']:
    if marker not in s: raise SystemExit('Missing verification marker: '+marker)
for name in ['readEmployeeLocalBackup','writeEmployeeLocalBackup','saveToLocalStorage','initCloudSync']:
    if len(re.findall(r'function '+name+r'\s*\(',s))!=1: raise SystemExit('Duplicate/missing function: '+name)
p.write_text(s,encoding='utf-8');print('FINAL SECURITY HARDENING PASSED')
