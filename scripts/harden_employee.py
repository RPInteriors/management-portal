from pathlib import Path
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
          userProfiles: USER_PROFILES,
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
              console.warn(
                "RPI protection: no employee backup available; refusing empty overwrite.",
              );
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
          USER_PROFILES = {
            ...DEFAULT_USER_PROFILES,
            ...(data.userProfiles || {}),
          };
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

required = [
    'function readEmployeeLocalBackup()',
    'function writeEmployeeLocalBackup(employeeList)',
    'BLOCKED an empty employee overwrite',
    'database.ref("portalData/employees")',
]
for marker in required:
    if marker not in patched:
        raise SystemExit(f'Missing protection marker: {marker}')

if patched.count('function readEmployeeLocalBackup()') != 1:
    raise SystemExit('Employee backup reader is duplicated')
if patched.count('function writeEmployeeLocalBackup(employeeList)') != 1:
    raise SystemExit('Employee backup writer is duplicated')
if patched.count('function saveToLocalStorage()') != 1:
    raise SystemExit('saveToLocalStorage is duplicated')
if patched.count('function initCloudSync()') != 1:
    raise SystemExit('initCloudSync is duplicated')

p.write_text(patched, encoding='utf-8')
print('Employee protection patch applied cleanly')
