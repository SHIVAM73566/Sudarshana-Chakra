import subprocess
import sys


def main() -> int:
    print("Installing requirements...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

    print("Installing Playwright browsers...")
    subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)

    print("\nSetup complete! Run 'python main.py' or start_sudarshana.bat to start Sudarshana Chakra.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
