#!/usr/bin/env python3
"""
Script to help publish kport to PyPI
"""
import subprocess
import sys
import os


def run_command(cmd, description):
    """Run a shell command and print status"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"❌ Failed: {description}")
        sys.exit(1)
    print(f"✅ Success: {description}")
    return result


def check_requirements():
    """Check if required packages are installed"""
    print("\n📦 Checking required packages...")
    
    required = ['build', 'twine']
    missing = []
    
    for package in required:
        result = subprocess.run(
            f"pip show {package}",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode != 0:
            missing.append(package)
    
    if missing:
        print(f"⚠️  Missing packages: {', '.join(missing)}")
        install = input("Install missing packages? (y/N): ")
        if install.lower() in ['y', 'yes']:
            run_command(
                f"pip install {' '.join(missing)}",
                f"Installing {', '.join(missing)}"
            )
        else:
            print("❌ Cannot proceed without required packages")
            sys.exit(1)
    else:
        print("✅ All required packages installed")


def clean_build():
    """Clean previous build artifacts"""
    print("\n🧹 Cleaning previous builds...")
    dirs = ['dist', 'build', 'kport.egg-info']
    for d in dirs:
        if os.path.exists(d):
            if sys.platform == 'win32':
                subprocess.run(f'rmdir /s /q {d}', shell=True)
            else:
                subprocess.run(f'rm -rf {d}', shell=True)
    print("✅ Cleaned build directories")


def build_package():
    """Build the package"""
    run_command("python -m build", "Building package")


def upload_to_test_pypi():
    """Upload to Test PyPI first"""
    print("\n📤 Uploading to Test PyPI (test.pypi.org)...")
    print("Note: You need a Test PyPI account at https://test.pypi.org/")
    proceed = input("Proceed with Test PyPI upload? (y/N): ")
    
    if proceed.lower() in ['y', 'yes']:
        run_command(
            "python -m twine upload --repository testpypi dist/*",
            "Uploading to Test PyPI"
        )
        print("\n✅ Upload successful!")
        print("Test installation with:")
        print("  pip install --index-url https://test.pypi.org/simple/ kport")


def upload_to_pypi():
    """Upload to production PyPI"""
    print("\n📤 Uploading to PyPI (pypi.org)...")
    print("⚠️  WARNING: This will publish to production PyPI!")
    print("Note: You need a PyPI account at https://pypi.org/")
    proceed = input("Proceed with PyPI upload? (y/N): ")
    
    if proceed.lower() in ['y', 'yes']:
        run_command(
            "python -m twine upload dist/*",
            "Uploading to PyPI"
        )
        print("\n🎉 Successfully published to PyPI!")
        print("Users can now install with:")
        print("  pip install kport")


def create_github_release():
    """Instructions for creating GitHub release"""
    print("\n📦 Creating GitHub Release")
    print("="*60)
    print("To create a GitHub release:")
    print("1. Push your code to GitHub")
    print("2. Go to: https://github.com/farman20ali/port-killer/releases/new")
    print("3. Create a new tag (e.g., v1.0.0)")
    print("4. Add release notes")
    print("5. Attach dist files (optional)")
    print("\nUsers can then install with:")
    print("  pip install git+https://github.com/farman20ali/port-killer.git")


def main():
    """Main function"""
    print("="*60)
    print("🚀 kport Publishing Tool")
    print("="*60)
    
    print("\nWhat would you like to do?")
    print("1. Check requirements and build package")
    print("2. Build and upload to Test PyPI (recommended first)")
    print("3. Build and upload to PyPI (production)")
    print("4. Show GitHub release instructions")
    print("5. Do everything (build + test + production)")
    print("0. Exit")
    
    choice = input("\nEnter your choice (0-5): ").strip()
    
    if choice == '0':
        print("👋 Goodbye!")
        sys.exit(0)
    
    if choice in ['1', '2', '3', '5']:
        check_requirements()
        clean_build()
        build_package()
    
    if choice in ['2', '5']:
        upload_to_test_pypi()
    
    if choice in ['3', '5']:
        if choice == '5':
            print("\n⚠️  Test PyPI upload completed.")
            proceed = input("Continue to production PyPI? (y/N): ")
            if proceed.lower() not in ['y', 'yes']:
                print("Stopped before production upload")
                sys.exit(0)
        upload_to_pypi()
    
    if choice == '4':
        create_github_release()
    
    if choice not in ['0', '1', '2', '3', '4', '5']:
        print("❌ Invalid choice")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("✅ All done!")
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
