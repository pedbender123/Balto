import openpyxl
import os

f = "testes/planilhas/Relatorio_Originais.xlsx"
if os.path.exists(f):
    wb = openpyxl.load_workbook(f)
    ws = wb.active
    # Read first data row (row 2)
    print(f"Row 2: {ws['B2'].value}")
else:
    print("File not found")
