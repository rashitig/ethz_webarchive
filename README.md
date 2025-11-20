# ethz_webarchive
Some code to help with processing the webarchive files of ETH Zürich

Clone the repository

```
ssh git@github.com:rashitig/ethz_webarchive.git
```
Set up the environment
```
conda create -n "env_warc" python=3.10 ipython
```
or
```
python3.10 -m venv env_warc
```
then activate the environment
```
conda activate env_warc
```
or
```
source env_warc/bin/activate
```
then install the requirements
```
pip install -r requirements.txt
```

Run `python prep_warc_files.py` after setting the filepaths.