import sys
import re
from pathlib import Path

# Hedef tarama dizini (repo root'undan itibaren)
FIXTURE_DIR = Path("tests/fixtures")

def is_authentic_tckn(tckn: str) -> bool:
    """Geçerli bir TCKN algoritmasına uyup uymadığını kontrol eder."""
    if len(tckn) != 11 or not tckn.isdigit() or tckn[0] == '0':
        return False
    digits = [int(d) for d in tckn]
    sum_odd = sum(digits[0:9:2])
    sum_even = sum(digits[1:8:2])
    check_10 = ((sum_odd * 7) - sum_even) % 10
    check_11 = sum(digits[0:10]) % 10
    return check_10 == digits[9] and check_11 == digits[10]

def is_authentic_msisdn(msisdn: str) -> bool:
    """Gerçek bir operatör numarası olup olmadığını kontrol eder."""
    clean_num = re.sub(r'[\s\-]', '', msisdn)
    if len(clean_num) != 10 or not clean_num.startswith('5'):
        return False
    # 555 sentetik test bloğudur, gerçek kabul edilmez
    if clean_num.startswith('555'):
        return False
    # Diğer 5XX blokları gerçek kabul edilerek bloklanacak
    return True

def scan_file_for_leaks(file_path: Path) -> list[str]:
    content = file_path.read_text(encoding="utf-8")
    violations = []
    
    # 11 Haneli Sayılar (TCKN Adayları)
    for match in re.finditer(r'\b[1-9]\d{10}\b', content):
        if is_authentic_tckn(match.group()):
            violations.append(f"Authentic TCKN detected: {match.group()}")
            
    # 10 Haneli Telefon Numaraları (MSISDN Adayları)
    for match in re.finditer(r'\b5\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b', content):
        if is_authentic_msisdn(match.group()):
            violations.append(f"Authentic MSISDN detected: {match.group()}")
            
    # Plaka (Sadece geçerli 01-81 il kodlarını yakalar)
    for match in re.finditer(r'\b(0[1-9]|[1-7][0-9]|8[0-1])[\s\-]*[A-Z]{1,3}[\s\-]*\d{2,4}\b', content):
        violations.append(f"Authentic Turkish Plate detected: {match.group()}")
        
    return violations

def run_guard():
    if not FIXTURE_DIR.exists():
        print(f"Skipping guard: {FIXTURE_DIR} not found.")
        sys.exit(0)
        
    has_errors = False
    print("Running Synthetic-Fixture Guard...")
    
    for filepath in FIXTURE_DIR.rglob("*.*"):
        if filepath.suffix in [".json", ".yaml", ".csv", ".txt"]:
            leaks = scan_file_for_leaks(filepath)
            if leaks:
                has_errors = True
                print(f"\n[CRITICAL] Data leakage detected in: {filepath}")
                for leak in leaks:
                    print(f"  - {leak}")
                    
    if has_errors:
        print("\nGuard Failed: Authentic PII data must not be committed to the repository!")
        print("Use synthetic test data (e.g., invalid TCKN checksums, 555 prefix MSISDNs, >81 plate codes).")
        sys.exit(1)
    else:
        print("Guard Passed: No authentic PII detected in fixtures.")
        sys.exit(0)

if __name__ == "__main__":
    run_guard()