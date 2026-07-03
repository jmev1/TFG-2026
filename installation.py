import subprocess
import sys

def instalar_requirements():
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
    ])

if __name__ == "__main__":
    instalar_requirements()
    print("Todas las librerías instaladas")