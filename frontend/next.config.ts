import type { NextConfig } from 'next';
const config:NextConfig={async rewrites(){return [{source:'/api/:path*',destination:`${process.env.TRUESTATE_FASTAPI_URL||'http://127.0.0.1:8080'}/api/:path*`}];}};
export default config;
