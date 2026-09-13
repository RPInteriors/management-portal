from pathlib import Path
import re
import shutil
import subprocess

p = Path('index.html')
text = p.read_text(encoding='utf-8')
Path('backups').mkdir(exist_ok=True)
short_sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
shutil.copy2(p, Path('backups') / f'index-before-production-hardening-{short_sha}.html')

# 1) Remove client-side password storage and make Firebase Auth authoritative.
text = re.sub(
    r'      const DEFAULT_USER_PROFILES = \{.*?      \};',
    '''      const DEFAULT_USER_PROFILES = {\n        CEO: "",\n        Administrator: "",\n        Supervisor: "",\n      };''',
    text,
    count=1,
    flags=re.S,
)

# 2) Protect employee persistence and never include userProfiles in general saves.
a = text.find('      // --- STORAGE LOGIC ---')
b = text.find('      function initUserProfilesSync() {', a)
if min(a, b) < 0:
    raise SystemExit('Storage markers missing')

storage = '''      // --- STORAGE LOGIC ---
      function readEmployeeLocalBackup() {
        try {
          const raw = localStorage.getItem("RPI_employee_backup");
          const parsed = raw ? JSON.parse(raw) : [];
          return Array.isArray(parsed) && parsed.length > 0 ? sortEmployeesById(parsed) : [];
        } catch (error) {
          console.warn("RPI employee backup read failed:", error);
          return [];
        }
      }

      function writeEmployeeLocalBackup(employeeList) {
        if (!Array.isArray(employeeList) || employeeList.length === 0) return;
        try {
          const safeList = sortEmployeesById(employeeList);
          localStorage.setItem("RPI_employee_backup", JSON.stringify(safeList));
          localStorage.setItem("RPI_employee_backup_time", new Date().toISOString());
        } catch (error) {
          console.warn("RPI local employee backup failed:", error);
        }
      }

      function saveToLocalStorage() {
        let safeEmployees = Array.isArray(employees) ? sortEmployeesById(employees) : [];
        const backupEmployees = readEmployeeLocalBackup();
        if (safeEmployees.length === 0 && backupEmployees.length > 0) {
          safeEmployees = backupEmployees;
          employees = safeEmployees;
        }
        const updates = { projects, expenseRecords, materialRecords };
        if (safeEmployees.length > 0) {
          employees = safeEmployees;
          updates.employees = safeEmployees;
          writeEmployeeLocalBackup(safeEmployees);
        } else {
          console.warn("RPI protection: BLOCKED an empty employee overwrite. Employee data was not changed in Firebase.");
        }
        return database.ref("portalData").update(updates).catch((error) => {
          console.error("Cloud Sync Error:", error);
          throw error;
        });
      }

'''
text = text[:a] + storage + text[b:]

# 3) Do not read the legacy plaintext password table.
a = text.find('      function initUserProfilesSync() {')
b = text.find('      async function applyForcedCodePasswords()', a)
if min(a, b) < 0:
    raise SystemExit('User profile markers missing')
text = text[:a] + '''      function initUserProfilesSync() {
        // Passwords are managed exclusively by Firebase Authentication.
        USER_PROFILES = { ...DEFAULT_USER_PROFILES };
      }

''' + text[b:]

# Disable legacy code-password recovery.
a = text.find('      async function applyForcedCodePasswords() {')
b = text.find('      function ', a + 10)
if a >= 0 and b >= 0:
    text = text[:a] + '''      async function applyForcedCodePasswords() {
        throw new Error("Legacy code-password recovery is disabled. Use Firebase Authentication credentials instead.");
      }

''' + text[b:]

# 4) Remove automatic sign-in using source-code passwords.
a = text.find('      async function ensureForceSyncAuthSession() {')
b = text.find('      async function syncRolePasswordToFirebaseAuth(', a)
if min(a, b) >= 0:
    text = text[:a] + '''      async function ensureForceSyncAuthSession() {
        if (!auth.currentUser) return null;
        currentUserRole = getCurrentSignedInRole();
        return currentUserRole;
      }

''' + text[b:]

# 5) Authenticate the main login against Firebase Authentication.
a = text.find('      function handleGlobalLogin() {')
b = text.find('      function closeLogin()', a)
if min(a, b) < 0:
    raise SystemExit('Global login markers missing')
login = '''      async function handleGlobalLogin() {
        const role = document.getElementById("userRole").value;
        const pass = document.getElementById("globalPassword").value.trim();
        const errorMsg = document.getElementById("loginError");
        if (!role || !pass) {
          errorMsg.textContent = "Please choose a role and enter password.";
          errorMsg.style.display = "block";
          return;
        }
        const email = getRoleEmail(role);
        if (!email) {
          errorMsg.textContent = "This role is not configured for Firebase Authentication.";
          errorMsg.style.display = "block";
          return;
        }
        try {
          const credential = await auth.signInWithEmailAndPassword(email, pass);
          currentUserRole = getCurrentSignedInRole();
          if (!credential.user || currentUserRole !== role) {
            await auth.signOut();
            throw new Error("Authenticated account does not match selected role.");
          }
          await database.ref("portalData/userProfiles").remove().catch((error) =>
            console.warn("Legacy user profile cleanup was not permitted:", error),
          );
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

'''
text = text[:a] + login + text[b:]

# 6) Administrator gate re-verifies against Firebase Auth.
a = text.find('      function login() {')
b = text.find('      function closeLogin()', a)
if min(a, b) < 0:
    raise SystemExit('Administrator login markers missing')
admin_login = '''      async function login() {
        const pass = document.getElementById("adminPassword").value.trim();
        if (currentUserRole !== "Administrator") {
          alert("Access Denied: Administrator profile required!");
          return;
        }
        try {
          if (!(await verifyRolePasswordInFirebaseAuth("Administrator", pass))) {
            throw new Error("Invalid administrator credentials.");
          }
          document.getElementById("loginOverlay").style.display = "none";
          document.getElementById("adminPassword").value = "";
          showPage("page4");
        } catch (error) {
          console.error("Administrator verification failed:", error);
          alert("Access Denied: Administrator profile required!");
        }
      }

'''
text = text[:a] + admin_login + text[b:]

# 7) Cloud sync must ignore legacy password data completely.
a = text.find('      function initCloudSync() {')
b = text.find('      // --- AUTH LOGIC ---', a)
if min(a, b) < 0:
    raise SystemExit('Cloud sync markers missing')
sync = '''      function initCloudSync() {
        const employeeRef = database.ref("portalData/employees");
        employeeRef.on("value", (snapshot) => {
          const cloudEmployees = snapshot.val();
          if (Array.isArray(cloudEmployees) && cloudEmployees.length > 0) {
            employees = sortEmployeesById(cloudEmployees);
            writeEmployeeLocalBackup(employees);
          } else {
            const backupEmployees = readEmployeeLocalBackup();
            if (backupEmployees.length > 0) {
              employees = backupEmployees;
              employeeRef.set(employees).catch((error) => console.error("RPI employee recovery write failed:", error));
            } else {
              console.warn("RPI protection: no employee backup available; refusing empty overwrite.");
            }
          }
          const activePage = Array.from(document.querySelectorAll(".page")).find((page) => page.style.display === "block")?.id;
          if (activePage === "page1") renderEmployeeList();
          if (activePage === "page4") renderAdminPanel();
        });
        database.ref("portalData").on("value", (snapshot) => {
          const data = snapshot.val();
          if (!data) return;
          projects = data.projects || [];
          expenseRecords = data.expenseRecords || [];
          materialRecords = data.materialRecords || [];
          normalizeProjectsData();
          const activePage = Array.from(document.querySelectorAll(".page")).find((page) => page.style.display === "block")?.id;
          if (activePage === "page1") renderEmployeeList();
          if (activePage === "pageExpense") renderExpenses();
          if (activePage === "pageMaterials") renderMaterials();
          if (activePage === "page3") renderProjectDashboard();
          if (activePage === "page4") renderAdminPanel();
        });
      }

'''
text = text[:a] + sync + text[b:]

# 8) Old-password change flow verifies against Firebase Auth instead of the database.
text = text.replace(
    '        if (USER_PROFILES[role] !== oldPassword) {\n          alert("Old password is incorrect.");\n          return;\n        }',
    '        if (!(await verifyRolePasswordInFirebaseAuth(role, oldPassword))) {\n          alert("Old password is incorrect.");\n          return;\n        }',
)
text = re.sub(
    r'          USER_PROFILES\[role\] = password;\n          await database\.ref\("portalData/userProfiles"\)\.set\(USER_PROFILES\);',
    '          await syncRolePasswordToFirebaseAuth(role, oldPassword, password);',
    text,
)

# Hard fail if any plaintext password or legacy password persistence remains in production source.
for forbidden in [
    'im@ceo!26',
    'im_the_admin+85',
    'wise_supervisor%94',
    'USER_PROFILES[role] = password;',
    'userProfiles: USER_PROFILES',
    'data.userProfiles',
    'presetPassword = DEFAULT_USER_PROFILES',
]:
    if forbidden in text:
        raise SystemExit(f'Forbidden insecure pattern remains: {forbidden}')

for marker in [
    'function readEmployeeLocalBackup()',
    'function writeEmployeeLocalBackup(employeeList)',
    'BLOCKED an empty employee overwrite',
    'database.ref("portalData/employees")',
    'auth.signInWithEmailAndPassword(email, pass)',
    'verifyRolePasswordInFirebaseAuth("Administrator", pass)',
]:
    if marker not in text:
        raise SystemExit(f'Missing verification marker: {marker}')

for name in ['readEmployeeLocalBackup', 'writeEmployeeLocalBackup', 'saveToLocalStorage', 'initCloudSync']:
    if len(re.findall(r'function ' + re.escape(name) + r'\s*\(', text)) != 1:
        raise SystemExit(f'Duplicate or missing function: {name}')

p.write_text(text, encoding='utf-8')
print('Production security hardening applied successfully')
