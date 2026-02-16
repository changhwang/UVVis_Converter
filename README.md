# uvvis_converter

UV-Vis DSW 데이터를 CSV로 변환하고, 샘플별 분석 결과 및 피규어를 생성하는 스크립트 모음입니다.

## 주요 스크립트

- `converter.py`
  - DSW -> CSV 변환
  - 샘플명 규칙(`xx-yyy-t()h-zz`) 기반 그룹화
  - 샘플별 결과 생성:
    - `raw.csv`
    - `baseline_corrected.csv`
    - `lambda_max.csv`
    - `fresh.csv`
    - `spectral_decay.csv`
    - `spectral_decay_map.csv`
    - `analysis.csv`
- `plot_figures.py`
  - `data/processed/<group>/` 결과를 읽어 피규어 생성
  - 출력: `figures/true_absorbance_overlay.png` 등

## 데이터 규칙

- 입력 DSW: `data/raw/*.DSW`
- baseline: `blank.DSW`
- 파장 처리 하한: `290 nm` 이상
- 피크 탐색 하한: `290 nm` 이상

## 설치

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 실행

1) 전체 변환 + 분석

```powershell
.\venv\Scripts\python.exe converter.py
```

2) 기존 CSV 재사용(변환 생략)

```powershell
.\venv\Scripts\python.exe converter.py --skip-convert
```

3) 피규어 생성(전체 그룹)

```powershell
.\venv\Scripts\python.exe plot_figures.py
```

4) 피규어 생성(특정 그룹)

```powershell
.\venv\Scripts\python.exe plot_figures.py --group TT-127-1
```

## 참고

- `data/`와 `venv/`는 `.gitignore`에 포함되어 있어 Git 추적 대상이 아닙니다.
