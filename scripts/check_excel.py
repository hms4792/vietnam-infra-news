#!/usr/bin/env python3
import openpyxl, os, sys

excel_path = os.environ.get('EXCEL_PATH',
    'data/database/Vietnam_Infra_News_Database_Final.xlsx')

if not os.path.exists(excel_path):
    print(f"❌ Excel 파일 없음: {excel_path}")
    sys.exit(1)

size = os.path.getsize(excel_path)
print(f"✅ Excel 파일 확인: {excel_path} ({size:,} bytes)")

wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
ws = wb.active
rows = ws.max_row - 1
print(f"News Database 행수: {rows}건")
wb.close()
