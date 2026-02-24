import re
import sys

def main():
    path = "openshift/base/05-monitoring.yaml"
    try:
        with open(path, 'r') as f:
            content = f.read()
        if re.search(r"path:\s*/metrics", content) or "/metrics" in content:
            print("ServiceMonitor path (/metrics) found in 05-monitoring.yaml")
            return 0
        else:
            print("WARN: /metrics path not found in 05-monitoring.yaml")
            return 2
    except FileNotFoundError:
        print("05-monitoring.yaml not found")
        return 1

if __name__ == "__main__":
    sys.exit(main())
