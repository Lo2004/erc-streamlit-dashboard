# 基准 ERC 看板

Streamlit MVP for the baseline ERC portfolio.

## Local Run

```bash
conda run -n pydata streamlit run app.py
```

## Data

The app reads Wind's standard multi-row-header export:

```text
data/标准 ERC- 收盘价数据.xlsx
```

Required codes:

```text
H20955.CSI
CBA00661.CS
CI005213.WI
H00300.CSI
AU9999.SGE
```

The custom ERC tab accepts the same Wind export format. If no file is uploaded,
the demo file below is used:

```text
data/测试拓展资产集.xlsx
```

## Deploy

Push this folder to GitHub, then create a Streamlit Community Cloud app with `app.py` as the entry file.
