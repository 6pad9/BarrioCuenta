"""Procesa cortes pendientes cada minuto. Ejecutar como proceso separado."""
import time
from .app import create_app

if __name__=='__main__':
    app=create_app()
    while True:
        result=app.test_cli_runner().invoke(args=['process-cuts'])
        if result.exit_code:
            print('No se completó el corte:',result.output,flush=True)
        else:
            print(result.output.strip(),flush=True)
        time.sleep(60)
