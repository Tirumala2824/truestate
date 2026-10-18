import type {NextConfig} from 'next';
// Standard Next.js is an optional frontend transport. Vinext/Sites uses the native D1 routes.
// When running `next dev`, rewrite API calls to the local FastAPI process.
const config:NextConfig={async rewrites(){return process.env.TRUESTATE_FASTAPI_URL?[{source:'/api/:path*',destination:`${process.env.TRUESTATE_FASTAPI_URL}/api/:path*`}]:[];}};
export default config;
