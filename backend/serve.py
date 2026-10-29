"""Windows WSGI entry point. The optional demo database must be explicitly named."""
import sys,os,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from waitress import serve
from .app import create_app

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=5000)
    parser.add_argument('--database')
    parser.add_argument('--demo',action='store_true')
    args=parser.parse_args()
    if args.demo and (not args.database or not args.database.startswith('sqlite:///')):
        parser.error('--demo requiere una base SQLite explícita de pruebas.')
    app=create_app(args.database,testing=args.demo)
    if args.demo:
        from .seed import seed
        seed(app)
    serve(app,host='127.0.0.1',port=args.port,threads=8,trusted_proxy='127.0.0.1',trusted_proxy_headers={'x-forwarded-proto','x-forwarded-host','x-forwarded-for'},clear_untrusted_proxy_headers=True)

if __name__=='__main__':main()
