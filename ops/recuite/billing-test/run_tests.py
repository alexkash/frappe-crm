"""Frappe v15 can exit zero after a failed unittest suite; check its summary."""

import argparse
import re
import subprocess


def succeeded(output, returncode):
	return (
		returncode == 0
		and bool(re.search(r"^Ran [1-9]\d* tests? in ", output, re.M))
		and bool(re.search(r"^OK(?:\s|$)", output, re.M))
		and not re.search(r"^FAILED\b", output, re.M)
	)


if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("--app", choices=["crm", "recuite_billing"], default="recuite_billing")
	parser.add_argument("--module")
	args = parser.parse_args()
	command = ["bench", "--site", "test_site", "run-tests", "--app", args.app]
	if args.module:
		command.extend(["--module", args.module])
	result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
	print(result.stdout, end="")
	raise SystemExit(0 if succeeded(result.stdout, result.returncode) else 1)
