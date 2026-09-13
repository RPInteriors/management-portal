from pathlib import Path
import re, shutil, subprocess

p = Path('index.html')
s = p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
sha = subprocess.check_output(['git','rev-parse','--short','HEAD'], text=True).strip()
shutil.copy2(p, Path('backups') / f'index-before-production-hardening-v2-{sha}.html')

def replace_region(src, start, end, replacement, label):
    a = src.find(start)
    b = src.find(end, a + len(start))
    if a < 0 or b < 0: raise SystemExit(f'{label} markers missing')
    return src[:a] + replacement + src[b:]

s = re.sub(r'      const DEFAULT_USER_PROFILES = \{.*?      \};', '''      const DEFAULT_USER_PROFILES = {\n        CEO: "",\n        Administrator: "",\n        Supervisor: "",\n      };''', s, count=1, flags=re.S)

storage = '''      // --- STORAGE LOGIC ---
      function readEmployeeLocalBackup() {
        try {
          const raw = localStorage.getItem("RPI_employee_backup");
          const parsed = raw ? JSON.parse(raw) : [];
          return Array.isArray(parsed) && parsed.length > 0 ? sortEmployeesById(parsed) : [];
        } catch (error) { console.warn("RPI employee backup read failed:", error); return []; }
      }
      function writeEmployeeLocalBackup(employeeList) {
        if (!Array.isArray(employeeList) || employeeList.length === 0) return;
        try {
          const safeList = sortEmployeesById(employeeList);
          localStorage.setItem("RPI_employee_backup", JSON.stringify(safeList));
          localStorage.setItem("RPI_employee_backup_time", new Date().toISOString());
        } catch (error) { console.warn("RPI local employee backup failed:", error); }
      }
      function saveToLocalStorage() {
        let safeEmployees = Array.isArray(employees) ? sortEmployeesById(employees) : [];
        const backupEmployees = readEmployeeLocalBackup();
        if (safeEmployees.length === 0 && backupEmployees.length > 0) { safeEmployees = backupEmployees; employees = safeEmployees; }
        const updates = { projects, expenseRecords, materialRecords };
        if (safeEmployees.length > 0) {
          employees = safeEmployees; updates.employees = safeEmployees; writeEmployeeLocalBackup(safeEmployees);
        } else {
          console.warn("RPI protection: BLOCKED an empty employee overwrite. Employee data was not changed in Firebase.");
        }
        return database.ref("portalData").update(updates).catch(error => { console.error("Cloud Sync Error:", error); throw error; });
      }

'''
s = replace_region(s, '      // --- STORAGE LOGIC ---', '      function initUserProfilesSync() {', storage, 'storage')

user_sync = '''      function initUserProfilesSync() {
        // Passwords are managed exclusively by Firebase Authentication.
        USER_PROFILES = { ...DEFAULT_USER_PROFILES };
      }

'''
s = replace_region(s, '      function initUserProfilesSync() {', '      async function applyForcedCodePasswords()', user_sync, 'user sync')

force = '''      async function applyForcedCodePasswords() {
        throw new Error("Legacy code-password recovery is disabled. Use Firebase Authentication credentials instead.");
      }

'''
s = replace_region(s, '      async function applyForcedCodePasswords()', '      function ', force, 'legacy recovery')

# Replace auto-sign-in helper without requiring source-code passwords.
a = s.find('      async function ensureForceSyncAuthSession() {')
b = s.find('      async function syncRolePasswordToFirebaseAuth(', a)
if a >= 0 and b >= 0:
    s = s[:a] + '''      async function ensureForceSyncAuthSession() {
        if (!auth.currentUser) return null;
        currentUserRole = getCurrentSignedInRole();
        return currentUserRole;
      }

''' + s[b:]

login_re = re.compile(r'(?ms)^      (?:async )?function handleGlobalLogin\(\) \{.*?^      \}\n\n      function closeLogin')
login = '''      async function handleGlobalLogin() {
        const role = document.getElementById("userRole").value;
        const pass = document.getElementById("globalPassword").value.trim();
        const errorMsg = document.getElementById("loginError");
        if (!role || !pass) { errorMsg.textContent = "Please choose a role and enter password."; errorMsg.style.display = "block"; return; }
        const email = getRoleEmail(role);
        if (!email) { errorMsg.textContent = "This role is not configured for Firebase Authentication."; errorMsg.style.display = "block"; return; }
        try {
          const credential = await auth.signInWithEmailAndPassword(email, pass);
          currentUserRole = getCurrentSignedInRole();
          if (!credential.user || currentUserRole !== role) { await auth.signOut(); throw new Error("Authenticated account does not match selected role."); }
          await database.ref("portalData/userProfiles").remove().catch(error => console.warn("Legacy user profile cleanup was not permitted:", error));
          sessionStorage.setItem("rp_auth_role", role);
          document.getElementById("globalPassword").value = "";
          errorMsg.style.display = "none";
          initApplication();
        } catch (error) {
          console.error("Firebase authentication failed:", error);
          errorMsg.textContent = "Invalid credentials or authentication unavailable.";
          errorMsg.style.display = "block";
        }
      }

      function closeLogin'''
s, n = login_re.subn(login, s, count=1)
if n != 1: raise SystemExit('Global login replacement failed')

admin_re = re.compile(r'(?ms)^      (?:async )?function login\(\) \{.*?^      \}\n\n      function closeLogin')
admin = '''      async function login() {
        const pass = document.getElementById("adminPassword").value.trim();
        if (currentUserRole !== "Administrator") { alert("Access Denied: Administrator profile required!"); return; }
        try {
          if (!(await verifyRolePasswordInFirebaseAuth("Administrator", pass))) throw new Error("Invalid administrator credentials.");
          document.getElementById("loginOverlay").style.display = "none";
          document.getElementById("adminPassword").value = "";
          showPage("page4");
        } catch (error) {
          console.error("Administrator verification failed:", error);
          alert("Access Denied: Administrator profile required!");
        }
      }

      function closeLogin'''
s, n = admin_re.subn(admin, s, count=1)
if n != 1: raise SystemExit('Administrator login replacement failed')

# Replace cloud sync so legacy plaintext userProfiles is neither read nor saved.
sync = '''      function initCloudSync() {
        const employeeRef = database.ref("portalData/employees");
        employeeRef.on("value", snapshot => {
          const cloudEmployees = snapshot.val();
          if (Array.isArray(cloudEmployees) && cloudEmployees.length > 0) {
            employees = sortEmployeesById(cloudEmployees); writeEmployeeLocalBackup(employees);
          } else {
            const backupEmployees = readEmployeeLocalBackup();
            if (backupEmployees.length > 0) { employees = backupEmployees; employeeRef.set(employees).catch(error => console.error("RPI employee recovery write failed:", error)); }
            else console.warn("RPI protection: no employee backup available; refusing empty overwrite.");
          }
          const activePage = Array.from(document.querySelectorAll(".page")).find(page => page.style.display === "block")?.id;
          if (activePage === "page1") renderEmployeeList();
          if (activePage === "page4") renderAdminPanel();
        });
        database.ref("portalData").on("value", snapshot => {
          const data = snapshot.val(); if (!data) return;
          projects = data.projects || []; expenseRecords = data.expenseRecords || []; materialRecords = data.materialRecords || [];
          normalizeProjectsData();
          const activePage = Array.from(document.querySelectorAll(".page")).find(page => page.style.display === "block")?.id;
          if (activePage === "page1") renderEmployeeList();
          if (activePage === "pageExpense") renderExpenses();
          if (activePage === "pageMaterials") renderMaterials();
          if (activePage === "page3") renderProjectDashboard();
          if (activePage === "page4") renderAdminPanel();
        });
      }

'''
s = replace_region(s, '      function initCloudSync() {', '      // --- AUTH LOGIC ---', sync, 'cloud sync')

s = s.replace('        if (USER_PROFILES[role] !== oldPassword) {\n          alert("Old password is incorrect.");\n          return;\n        }', '        if (!(await verifyRolePasswordInFirebaseAuth(role, oldPassword))) {\n          alert("Old password is incorrect.");\n          return;\n        }')
s = re.sub(r'          USER_PROFILES\[role\] = password;\n          await database\.ref\("portalData/userProfiles"\)\.set\(USER_PROFILES\);', '          await syncRolePasswordToFirebaseAuth(role, oldPassword, password);', s)

for bad in ['im@ceo!26','im_the_admin+85','wise_supervisor%94','USER_PROFILES[role] = password;','userProfiles: USER_PROFILES','data.userProfiles','presetPassword = DEFAULT_USER_PROFILES']:
    if bad in s: raise SystemExit(f'Forbidden insecure pattern remains: {bad}')
for marker in ['function readEmployeeLocalBackup()','function writeEmployeeLocalBackup(employeeList)','BLOCKED an empty employee overwrite','database.ref("portalData/employees")','auth.signInWithEmailAndPassword(email, pass)','verifyRolePasswordInFirebaseAuth("Administrator", pass)']:
    if marker not in s: raise SystemExit(f'Missing marker: {marker}')
for name in ['readEmployeeLocalBackup','writeEmployeeLocalBackup','saveToLocalStorage','initCloudSync']:
    if len(re.findall(r'function ' + re.escape(name) + r'\s*\(', s)) != 1: raise SystemExit(f'Duplicate/missing function: {name}')

p.write_text(s, encoding='utf-8')
print('Production security hardening v2 passed')
