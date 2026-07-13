@echo off
cd /d "%~dp0"
echo ============================================
echo  MODO DE TESTES - usando SQLite local
echo  (finance.db) - NAO toca no Supabase/producao
echo ============================================
set FORCE_LOCAL_DB=1
python -m streamlit run app.py --server.port 8503
