"""
Given warc files create md and text files.
using: https://github.com/recrm/ArchiveTools#warc-extractorpy
"""
import subprocess
import os
import shutil
import json
import re
import gzip
import pandas as pd
from bs4 import BeautifulSoup
from html_to_markdown import convert_to_markdown
from tqdm import tqdm


def get_base_site_from_url(url_in):
    """
    Extracts the base site from the given URL.
    Example: "http://ethz.ch/about/test.png" returns "ethz.ch"

    Args:
        url_in (str): The url to find the base site for.

    Returns:
        str: Base Url
    """
    if "//" not in url_in:
        base_site = url_in
    else:
        url_in_old = url_in
        base_site = url_in.split("//")[1]
        if base_site == "http:":
            print(f"This url is oddly formed: {url_in_old}")
            base_site = url_in_old.split("//")[2]

    # various artefacts found in the warc files
    base_site = base_site.replace("dns:", "")
    base_site = base_site.replace("mailto:", "")
    base_site = base_site.replace("www.", "")
    base_site = base_site.replace("www0.", "")
    base_site = base_site.replace("www1.", "")
    base_site = base_site.replace("www2.", "")
    base_site = base_site.replace("www3.", "")
    base_site = base_site.split(":")[0]
    base_site = base_site.split("/")[0]

    if base_site[-1] == ".":
        base_site = base_site[:-1]

    return base_site

def warc_to_html(input_dir_path: str, output_dir_path: str):
    """
    Goes through the files in `input_dir_path`, finds all the warc (and warc.gz) files,
    extracts the html pages and saves them in the given `output_dir_path`.
    The hierarchy of directories is preserved for the html output.

    Args:
        input_dir_path (str): Path to the input directory.
        output_dir_path (str): Path to the output directory.
    """
    subprocess.call(f"python warc_extractor.py http:content-type:text/html -dump content -error -path {input_dir_path} -output_path {output_dir_path}", shell=True)

def process_file(file, d, output_file_format, output_dir, base_site):
    """
    Given the html file extracts the text, does some cleanup and
    saves it under the base_site file.

    Args:
        file (str): File to be read and extracted.
        d (str): Directory path to the file.
        output_file_format (str): File format for the text output of the html file.
            Options: ["md", "txt"].
        output_dir (str, optional): Path to the output directory. If it is None, 
            the html file is saved in the same place the md file was found.
            Defaults to None.
        base_site (str): Base website URL.
            For "ethz.ch/staffnet/de" it would be "ethz.ch"
    
    Returns:
        None
    """
    if output_dir:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        out_path = output_dir+"/"+base_site+"."+output_file_format
    else:
        out_path = d+"/"+base_site+"."+output_file_format

    # We only handle html files, we do not consider any other type of website
    # content for topic modeling
    if file.endswith(".html") or file.endswith(".html.gz"):
        if file.endswith(".html.gz"):
            with gzip.open(d+"/"+file, "rb") as f_in_zipped:
                html = f_in_zipped.read()
        else:
            try:
                with open(d+"/"+file, "r", encoding="utf-8") as f_in:
                    html = f_in.read()
            except Exception:
                try:
                    with open(d+"/"+file, "r", encoding="unicode_escape") as f_in:
                        html = f_in.read()
                except UnicodeDecodeError:
                    with open("error_files.txt", "a+") as f_out_err:
                        print(f"This file could not be read: {d+"/"+file}", file=f_out_err)
                    return
        if html == "":
            return
        if output_file_format == "md":
            text = convert_to_markdown(html)
        else:  # above i make sure that there are only two options.
            soup = BeautifulSoup(html, features="html.parser")
            # kill all script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            # get text
            text = soup.get_text()
            # break into lines and remove leading and trailing space on each
            text = [line.strip() for line in text.splitlines()]
            # break multi-headlines into a line each
            text = [phrase.strip() for line in text for phrase in line.split("  ")]
            # drop blank lines
            text = '\n'.join(chunk for chunk in text if chunk)

        # Remove "empty" files
        if text in ("", "Redirecting"):
            return

        # Save output file
        # might be overkill, but check if this exact webpage is already verbatim in the file
        # for this website.
        with open(out_path, "a+", encoding="utf-8") as f_out:
            text_in = f_out.read()
            if text not in text_in:
                f_out.write(text)
        del text_in

def html_to_md_or_txt(cmi_coll_excel_path: str,
                      input_dir_path: str,
                      output_file_format: str,
                      coll_mappings_path: str,
                      output_dir=None,
                      filenames_to_remove=[
                          "impressum", "datenschutz", "kontakt", "robots",
                          "imprint", "data-protection", "contact", "copyright",
                      ]):
    """
    Converts html files to markdown or text files. Removes files that have certain keywords
    in their filenames.

    Args:
        cmi_coll_excel_path (str): Path to the exported cmi collection Excel file.
        input_dir_path (str): Path to the input directory where the html files are.
        output_file_format (str): File format for the text output of the html file.
            Options: ["md", "txt"].
        coll_mappings_path (str): Path to where to save the mapping json file to.
            The keys are what the website is called locally (for instance `ethz.ch`)
            and the values are what the website is called in our database (for instance
            `https://www.ethz.ch/`)
        output_dir (str, optional): Path to the output directory. If it is None, 
            the html file is saved in the same place the md file was found.
            Defaults to None.
        keywords_to_rm_filename (list, optional): List of keywords where, if these appear
            in the filename of the input html file, this file is not converted.
            Defaults to ["impressum", "datenschutz", "kontakt", "robots", "imprint",
            "data-protection", "contact"].

    Raises:
        ValueError: If the output file format is not a valid option.
    """
    output_file_format_types = ['md', 'txt']
    if output_file_format not in output_file_format_types:
        raise ValueError(
            "Invalid output_file_format type. Expected one of: {output_file_format_types}"
        )

    # get special urls
    coll_df = pd.read_excel(cmi_coll_excel_path)
    coll_df = coll_df.fillna("")
    coll_urls = list(coll_df["URL"])
    del coll_df

    subpages_base_sites = {}
    htmlpages_base_sites = {}
    coll_mappings = {}
    for url in coll_urls:
        if url != "":
            base_site = get_base_site_from_url(url)
            navig = url.split(base_site)
            if len(navig) >= 2:
                navig = navig[-1]
                if navig != "/":
                    if ".html" in navig:
                        if navig.endswith(".html"):
                            navig += "/"
                        htmlpages_base_sites.setdefault(base_site, []).append(
                            {"subpage": "/".join(navig.split("/")[:-2]),
                            "html_page": navig.split("/")[-2]}
                        )
                    else:
                        if navig.endswith("/"):
                            subpages_base_sites.setdefault(base_site, []).append(navig[:-1])
                        else:
                            subpages_base_sites.setdefault(base_site, []).append(navig)
                    if navig.endswith("/"):
                        coll_mappings[base_site+"_".join(navig.split("/"))[:-1]] = url
                    else:
                        coll_mappings[base_site+"_".join(navig.split("/"))] = url
                else:
                    coll_mappings[base_site] = url

    with open(coll_mappings_path, "w", encoding="utf-8") as f:
        json.dump(coll_mappings, f)

    list_ = list(os.walk(input_dir_path))
    for d,_,f in tqdm(list_):
        # what website we're processing
        base_site = get_base_site_from_url(d.split(".gz_")[-1])
        # we do the topic modeling per website so we save one file per website.
        # this means that we throw away the time axis

        # some websites have to be treated in a special manner
        # since their database has subsites for these websites
        # this isn't ideal at all but easier to understand and
        # change than solutions
        if base_site in subpages_base_sites:
            for subpg in subpages_base_sites[base_site]:
                if d.endswith(subpg):
                    for f_i in f:
                        process_file(f_i, d, output_file_format, output_dir, base_site+"_".join(subpg.split("/")))
        if base_site in htmlpages_base_sites:
            for htmldict in htmlpages_base_sites[base_site]:
                if d.endswith(htmldict["subpage"]):
                    for f_i in f:
                        html_page_cl = htmldict["html_page"].replace(".html", "")
                        if re.match(r"^("+html_page_cl+r"\.|"+html_page_cl+r"\()", f_i):
                            f_i_cleaned_name = f_i.split("(")[0]
                            f_i_cleaned_name = f_i_cleaned_name.split(".")[0] + ".html"
                            process_file(
                                f_i,
                                d,
                                output_file_format,
                                output_dir,
                                base_site+"_".join(htmldict["subpage"].split("/"))+"_"+f_i_cleaned_name
                            )

        if base_site in coll_mappings and base_site != "seismo.ethz.ch":
            # seismo is over 3 gigabites large.
            for file in f:
                # Remove files whose filenames contain certain keywords
                ignore_file = False
                for k in filenames_to_remove:
                    if k in file:
                        ignore_file = True
                        break
                if not ignore_file:
                    process_file(file, d, output_file_format, output_dir, base_site)

def warc_to_md(cmi_coll_excel_path: str,
               input_dir_path: str,
               coll_mappings_path:str,
               output_dir_path="./data"):
    """Convert the warc files in the given input dir path to .md files
    and save them in the given output dir path.

    Args:
        cmi_coll_excel_path (str): Path to the collection cmi export excel file.
        input_dir_path (str): Path to the input directory.
        coll_mappings_path (str): Path to where to save the mapping json file to.
            The keys are what the website is called locally (for instance `ethz.ch`)
            and the values are what the website is called in our database (for instance
            `https://www.ethz.ch/`)
        output_dir_path (str): Path to the output directory. Defaults to "./data".
    """
    warc_to_html(input_dir_path, COLL+"_htmltxtfiles")
    html_to_md_or_txt(cmi_coll_excel_path, COLL+"_htmltxtfiles", "md" , coll_mappings_path, output_dir_path)

def warc_to_string(cmi_coll_excel_path: str,
                   input_dir_path: str,
                   coll_mappings_path:str,
                   output_dir_path="./data"):
    """Convert the warc files in the given input dir path to .txt files
    and save them in the given output dir path.

    Args:
        cmi_coll_excel_path (str): Path to the collection cmi export excel file.
        input_dir_path (str): Path to the input directory.
        coll_mappings_path (str): Path to where to save the mapping json file to.
            The keys are what the website is called locally (for instance `ethz.ch`)
            and the values are what the website is called in our database (for instance
            `https://www.ethz.ch/`)
        output_dir_path (str): Path to the output directory. Defaults to "./data".
    """
    warc_to_html(input_dir_path, COLL+"_htmltxtfiles")
    html_to_md_or_txt(cmi_coll_excel_path, COLL+"_htmltxtfiles", "txt", coll_mappings_path, output_dir_path)

COLL="19945"
if __name__ == "__main__":
    warc_to_string("/home/genta/Downloads/2025-09-11_CMI-Export_Coll-"+COLL+".xlsx",
                   "/home/genta/mnt/adl/kizh/"+COLL+"",
                   "/home/genta/git/KIZH/Topic_Modeling/2025-10-06_"+COLL+"_mappings.json",
                   "./data/"+COLL
                   )
