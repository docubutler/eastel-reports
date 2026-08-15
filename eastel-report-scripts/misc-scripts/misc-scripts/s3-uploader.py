#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

# ============================================================
# Configuration
# ============================================================

S3_DESTINATION = "s3://anchor-prod-ap-southeast-5/build-images"
AWS_CLI = "aws"

# ============================================================


def pause():
    input("\nPress Enter to exit...")


def main():

    if len(sys.argv) < 2:
        print("Drag and drop one or more files onto this script.")
        pause()
        return

    if shutil.which(AWS_CLI) is None:
        print("ERROR: AWS CLI was not found.")
        print("Please ensure 'aws' is installed and available in PATH.")
        pause()
        return

    uploaded_count = 0

    for file_path in sys.argv[1:]:

        file_path = os.path.abspath(file_path)

        if not os.path.isfile(file_path):
            print(f"\nSkipping (not a file): {file_path}")
            continue

        filename = os.path.basename(file_path)
        uploaded_path = f"{S3_DESTINATION}/{filename}"

        print(f"\nUploading:\n{file_path}\n")

        cmd = [
            AWS_CLI,
            "s3",
            "cp",
            file_path,
            S3_DESTINATION
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:

            uploaded_count += 1

            print("=" * 70)
            print("SUCCESS")
            print()
            print("Your file is uploaded to:")
            print(uploaded_path)
            print("=" * 70)

            if CLIPBOARD_AVAILABLE:
                pyperclip.copy(uploaded_path)
                print("(Copied S3 path to clipboard)")

        else:

            print("=" * 70)
            print("UPLOAD FAILED")
            print("=" * 70)

            if result.stderr.strip():
                print(result.stderr.strip())
            else:
                print(result.stdout.strip())

    print(f"\nFinished. Uploaded {uploaded_count} file(s).")

    pause()


if __name__ == "__main__":
    main()