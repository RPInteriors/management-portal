from pathlib import Path
import re
import shutil
import subprocess

p = Path('index.html')
text = p.read_text(encoding='utf-8')

region_start = text.find('      // --- STORAGE LOGIC ---')
region_end = text.find('      function initUserProfilesSync() {', region_start)
sync_start = text.find('      function initCloudSync() {')
sync_end = text.find('      // --- AUTH LOGIC ---', sync_start)

if min(region_start, region_end, sync_start, sync_end) < 0:
    raise SystemExit('Required storage markers not found')

Path('backups').mkdir(exist_ok=True)
short_sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
shutil.copy2(p, Path('backups') / f'index-before-employee-protection-{short_sha}.html')

new_storage = '''      // --- STORAGE LOGIC ---
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
        const updates = {
          projects,
          expenseRecords,
          materialRecords,
        };
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

new_sync = '''      function initCloudSync() {
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
              employeeRef.set(employees).catch((error) =>
                console.error("RPI employee recovery write failed:", error),
              );
            } else {
              console.warn("RPI protection: no employee backup available; refusing empty overwrite.");
            }
          }
          const activePage = Array.from(document.querySelectorAll(".page")).find(
            (page) => page.style.display === "block",
          )?.id;
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
          const activePage = Array.from(document.querySelectorAll(".page")).find(
            (page) => page.style.display === "block",
          )?.id;
          if (activePage === "page1") renderEmployeeList();
          if (activePage === "pageExpense") renderExpenses();
          if (activePage === "pageMaterials") renderMaterials();
          if (activePage === "page3") renderProjectDashboard();
          if (activePage === "page4") renderAdminPanel();
        });
      }

'''

patched = text[:region_start] + new_storage + text[region_end:]
sync_start = patched.find('      function initCloudSync() {')
sync_end = patched.find('      // --- AUTH LOGIC ---', sync_start)
if min(sync_start, sync_end) < 0:
    raise SystemExit('Sync markers not found after storage normalization')
patched = patched[:sync_start] + new_sync + patched[sync_end:]

# Never keep passwords in the public application source.
patched = re.sub(
    r'      const DEFAULT_USER_PROFILES = \{.*?      \};',
    '''      const DEFAULT_USER_PROFILES = {\n        CEO: "",\n        Administrator: "",\n        Supervisor: "",\n      };''',
    patched,
    count=1,
    flags=re.S,
)
patched = patched.replace(
    '      const FORCE_CODE_PASSWORDS = false;',
    '      const FORCE_CODE_PASSWORDS = false; // Legacy flag retained only for compatibility; no passwords are stored in source.',
)

# Prevent legacy plaintext password data from being loaded back into the client.
user_sync_start = patched.find('      function initUserProfilesSync() {')
user_sync_end = patched.find('      async function applyForcedCodePasswords()', user_sync_start)
if min(user_sync_start, user_sync_end) < 0:
    raise SystemExit('User profile sync markers not found')
new_user_sync = '''      function initUserProfilesSync() {
        // Passwords are managed exclusively by Firebase Authentication.
        // Legacy portalData/userProfiles is intentionally not read.
        USER_PROFILES = { ...DEFAULT_USER_PROFILES };
      }

'''
patched = patched[:user_sync_start] + new_user_sync + patched[user_sync_end:]

# Disable the legacy hardcoded-password recovery switch.
force_start = patched.find('      async function applyForcedCodePasswords() {')
force_end = patched.find('      function ', force_start + 10)
if force_start >= 0 and force_end >= 0:
    patched = patched[:force_start] + '''      async function applyForcedCodePasswords() {
        throw new Error("Legacy code-password recovery is disabled. Use Firebase Authentication credentials instead.");
      }

''' + patched[force_end:]

# Do not auto-sign-in using passwords embedded in the client.
force_sync_start = patched.find('      async function ensureForceSyncAuthSession() {')
force_sync_end = patched.find('      async function syncRolePasswordToFirebaseAuth(', force_sync_start)
if min(force_sync_start, force_sync_end) >= 0:
    patched = patched[:force_sync_start] + '''      async function ensureForceSyncAuthSession() {
        if (!auth.currentUser) return null;
        currentUserRole = getCurrentSignedInRole();
        return currentUserRole;
      }

''' + patched[force_sync_end:]

# Global login must authenticate against Firebase Auth, never against a client-side password table.
login_pattern = re.compile(r'      function handleGlobalLogin\(\) \{.*?\n      \}\n\n      function closeLogin', re.S)
login_replacement = '''      async function handleGlobalLogin() {
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
            throw new Error("Authenticated account does not match the selected role.");
          }
          // Remove the legacy plaintext password table after a successful authenticated login.
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

      function closeLogin'''
patched, count = login_pattern.subn(login_replacement, patched, count=1)
if count != 1:
    raise SystemExit('Global login function replacement failed')

# Administrator secondary gate must verify the Firebase Authentication password, not a local password copy.
admin_pattern = re.compile(r'      function login\(\) \{.*?\n      \}\n\n      function closeLogin', re.S)
admin_replacement = '''      async function login() {
        const pass = document.getElementById("adminPassword").value.trim();
        if (currentUserRole !== "Administrator") {
          alert("Access Denied: Administrator profile required!");
          return;
        }
        try {
          const verified = await verifyRolePasswordInFirebaseAuth("Administrator", pass);
          if (!verified) throw new Error("Invalid administrator credentials.");
          document.getElementById("loginOverlay").style.display = "none";
          document.getElementById("adminPassword").value = "";
          showPage("page4");
        } catch (error) {
          console.error("Administrator verification failed:", error);
          alert("Access Denied: Administrator profile required!");
        }
      }

      function closeLogin'''
patched, count = admin_pattern.subn(admin_replacement, patched, count=1)
if count != 1:
    raise SystemExit('Admin login function replacement failed')

# Existing password-change flow can verify the old password directly against Firebase Auth.
patched = patched.replace(
    '        if (USER_PROFILES[role] !== oldPassword) {\n          alert("Old password is incorrect.");\n          return;\n        }',
    '        if (!(await verifyRolePasswordInFirebaseAuth(role, oldPassword))) {\n          alert("Old password is incorrect.");\n          return;\n        }',
)

# Password changes should update Firebase Authentication only; never persist plaintext passwords in Realtime Database.
patched = re.sub(
    r'          USER_PROFILES\[role\] = password;\n          await database\.ref\("portalData/userProfiles"\)\.set\(USER_PROFILES\);',
    '          await syncRolePasswordToFirebaseAuth(role, oldPassword, password);',
    patched,
)

# Any remaining legacy password-table write is a hard failure for this hardening patch.
required = [
    'function readEmployeeLocalBackup()',
    'function writeEmployeeLocalBackup(employeeList)',
    'BLOCKED an empty employee overwrite',
    'database.ref("portalData/employees")',
    'auth.signInWithEmailAndPassword(email, pass)',
    'verifyRolePasswordInFirebaseAuth("Administrator", pass)',
]
for marker in required:
    if marker not in patched:
        raise SystemExit(f'Missing hardening marker: {marker}')

for forbidden in [
    'im@ceo!26',
    'im_the_admin+85',
    'wise_supervisor%94',
    'USER_PROFILES[role] = password;',
    'userProfiles: USER_PROFILES',
    'data.userProfiles',
    'presetPassword = DEFAULT_USER_PROFILES',
]:
    if forbidden in patched:
        raise SystemExit(f'Forbidden insecure pattern remains: {forbidden}')

if patched.count('function readEmployeeLocalBackup()') != 1:
    raise SystemExit('Employee backup reader is duplicated')
if patched.count('function writeEmployeeLocalBackup(employeeList)') != 1:
    raise SystemExit('Employee backup writer is duplicated')
if patched.count('function saveToLocalStorage()') != 1:
    raise SystemExit('saveToLocalStorage is duplicated')
if patched.count('function initCloudSync()') != 1:
    raise SystemExit('initCloudSync is duplicated')

p.write_text(patched, encoding='utf-8')
print('Employee protection and authentication hardening patch applied cleanly')
