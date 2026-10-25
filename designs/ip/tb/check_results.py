import argparse
from xml.etree import ElementTree as ET

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--result-fname", default="results.xml")
    args = parser.parse_args()

    result = ET.parse(args.result_fname)
    for testsuite in result.iter("testsuite"):
        for testcase in testsuite.iter("testcase"):
            for _failure in testcase.iter("failure"):
                raise Exception(f"{testcase.get('name')}: Test Failed.")
    print("PASS")
