#!/bin/bash python
import argparse
import os
import json
import time
import logging
import fitz

st = time.time()

def process_text(filename, filepath):
    # time.sleep(180)

    output_folder = "/home/flask/app/output_files"
    all_paths = []

    file_at = f"{output_folder}/{filename}"
    if not os.path.exists(file_at):
        return []
    
    doc = fitz.open(file_at)
    for i in range(len(doc)):
        for img in doc.getPageImageList(i):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)

            file_out = f"{output_folder}/{filename}_p%s-%s.png" % (i, xref)
            all_paths.append(f"output_files/{filename}_p%s-%s.png" % (i, xref))

            if pix.n < 5:       # this is GRAY or RGB
                pix.writePNG(file_out)
            else:               # CMYK: convert to RGB first
                pix1 = fitz.Pixmap(fitz.csRGB, pix)
                pix1.writePNG(file_out)
                pix1 = None
            pix = None

    return all_paths

def main(id="", uuid="", filename="", filepath=""):
    processed_body = process_text(filename, filepath)
    ajson = {}
    return processed_body


usage = """
    Minimal app

	Usage:

    # Use text buffer
    python3 main.py -i id_of_item -t "text buffer" -l
	"""

if __name__ == "__main__":
    # Handle arguments
    parser = argparse.ArgumentParser(
        description="Minimal app",
        epilog=usage,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-i", help="Item id", type=str, default="1")
    parser.add_argument("-t", help="Text to be processed", type=str, default="")
    args = parser.parse_args()

    uuid = args.i
    body = args.t

    result = main(
        id="", uuid=uuid, filename=body, filepath=""
    )

    print(result)
    print("~~ finished in {0:.3f} sec ~~".format(time.time() - st))
