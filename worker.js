// Cloudflare Worker API scaffold. It intentionally returns no fabricated verdict.
// Before launch, connect a real video detector and enforce quotas server-side.
export default {
 async fetch(request, env) {
  const cors={"Access-Control-Allow-Origin":env.ALLOWED_ORIGIN||"*","Access-Control-Allow-Methods":"POST, OPTIONS","Access-Control-Allow-Headers":"Content-Type"};
  if(request.method==="OPTIONS")return new Response(null,{headers:cors});
  const url=new URL(request.url);
  if(url.pathname!=="/api/analyse"||request.method!=="POST")return Response.json({error:"Not found"},{status:404,headers:cors});
  // Required before production:
  // - durable server-side 3/day quota (browser storage is not secure)
  // - upload size/type/duration validation
  // - SSRF-safe URL validation and allowlisted fetch destinations
  // - permitted platform/API access; never evade login, DRM or platform controls
  // - provider API key stored as a Worker secret, never in frontend code
  // - privacy notice, retention policy and prompt deletion of uploaded media
  return Response.json({code:"DETECTOR_NOT_CONFIGURED",error:"The video detection provider has not been connected yet. No authenticity verdict was generated."},{status:503,headers:cors});
 }
};