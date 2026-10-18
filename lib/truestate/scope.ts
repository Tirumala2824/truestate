/** Fail-closed command grammar. Entire requests must match; keywords never grant scope. */
export const SCOPE_REFUSAL='This request is outside TRUESTATE’s supported scope. I can only help with supplier-payment investigations, financial evidence, payment review, audit reports, and this platform’s workflows. I cannot answer unrelated or general-purpose questions.';
export const SCOPE_VERSION='financial-workflows-v1';
export type ScopeDecision={allowed:boolean;canonical:string;documentTask?:boolean};
const supplier='(?:aster(?: components)?|nova(?: logistics)?|orion(?: manufacturing)?|cedar(?: consulting)?|veda(?: cloud services)?|kaveri(?: industrial)?|pinnacle(?: systems)?|helix(?: packaging)?)';
const ref='(?:ts[- ]?\\d{4,8}|pay[- ]?\\d{4,8})';
const caseSuffix=`(?: (?:for|of|in|about) ${ref})?`;
const request='(?:show(?: me)?|give me|display|list|inspect|view|open|check|review|explain|describe|tell me about)';
const exact=(s:string,p:string)=>new RegExp(`^(?:${p})$`,'u').test(s);
export function financialReason(reason:string){
 const words=reason.toLowerCase().normalize('NFKC').replace(/[.,:;'-]/g,' ').split(/\s+/).filter(Boolean);
 const permitted=new Set('i we our the a an this that it has have was were is are been by with through from to for of and after because using on pending independently independent verified verification verify confirmed confirmation confirm checked reviewed review trusted pre established supplier vendor contact account receiving bank payment invoice authorization authorised authorized signed contract history records evidence mismatch missing disputed precautionary hold release human reviewer completed resolved amount identity callback matched original new correct'.split(' '));
 return reason.length>=15&&reason.length<=500&&words.every(w=>permitted.has(w))&&words.some(w=>['verified','confirmed','mismatch','missing','disputed','pending','reviewed','checked'].includes(w))&&words.some(w=>['supplier','account','payment','invoice','evidence','authorization','contact'].includes(w));
}
export function scopeRequest(raw:string):ScopeDecision{
 const deny={allowed:false,canonical:''};if(typeof raw!=='string'||raw.length>4000||/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2060-\u206f]/.test(raw))return deny;
 let t=raw.normalize('NFKC').toLowerCase().replace(/[’‘]/g,"'").trim().replace(/[.!?]+$/,'').replace(/\s+/g,' ');
 // Only bounded politeness is removed. Roleplay, translations, encodings, and instructions remain unmatched.
 t=t.replace(/^(?:please |can you please |could you please |can you |could you |would you |i want you to |i want to )/,'').replace(/,? please$/,'');
 const yes=(canonical=t,documentTask=false):ScopeDecision=>({allowed:true,canonical,documentTask});
 if(exact(t,'(?:analy[sz]e|review|inspect|read|check|extract|summari[sz]e)(?: the| this| these| my| all)?(?: attached| uploaded)? (?:financial )?(?:documents?|files?|invoices?|receipts?|images?|attachments?)(?: for (?:payment risk|supplier payment risk|account changes|financial risk))?'))return yes('Review uploaded documents',true);
 if(exact(t,'(?:compare|check)(?: the| this| these)? (?:uploaded |attached )?(?:documents?|invoices?|attachments?)(?: with| against)(?: the| this| current| selected)? (?:payment|case|investigation)'))return yes('Compare uploaded documents with this payment',true);
 if(exact(t,`${request} (?:my |the )?(?:uploaded |attached )(?:documents?|files?|invoices?|evidence)`))return yes('Review uploaded documents',true);
 if(exact(t,'(?:how (?:do i|can i) (?:upload|attach) (?:an? |my )?(?:invoice|document|image|pdf)|(?:show|explain) (?:the )?(?:supported inputs|upload limits|streaming status|platform scope)|what (?:files|inputs) (?:do you|does truestate) support)'))return yes('Supported inputs');
 if(exact(t,`(?:investigate|check|review|start an? investigation (?:for|of)) ${supplier}(?:'s)?(?: suspicious)?(?: supplier)?(?: payment| account change| invoice)?`))return yes(`Investigate ${t.match(new RegExp(supplier))![0]}`);
 if(exact(t,'(?:run|start|launch|try|simulate|test|demonstrate)(?: the| a)? (?:coordinated(?: fraud| evidence manipulation)?|legitimate(?: bank change)?|genuine bank change|invoice manipulation|invoice mismatch|simple(?: fraud)?|insufficient(?: evidence)?|missing evidence|failed(?: containment)?|timeout)(?: (?:scenario|simulation|demo))?'))return yes(t);
 if(exact(t,`${request} (?:the |all |all the )?(?:five |5 )?(?:demo )?(?:scenarios|simulations|demo options)`))return yes('Show demo scenarios');
 if(exact(t,'(?:try|run|start) all (?:five|5|the) (?:demo )?scenarios'))return yes('Show demo scenarios');
 if(exact(t,'(?:what can i try|what are the demo options)'))return yes('Show demo scenarios');
 if(exact(t,'(?:reset (?:the )?(?:demo|environment|data)|start over|fresh seed)'))return yes('Reset the demo');
 if(exact(t,'(?:recover|resume)(?: the| an)?(?: interrupted)? (?:run|investigation)'))return yes('Recover interrupted investigation');
 if(exact(t,'(?:yes|confirm|approve|go ahead|proceed)(?: (?:release|hold|reset)(?: pay[- ]?\\d{4,8})?)?'))return yes(t);
 if(exact(t,"(?:cancel(?: this action| the action)?|no|never mind|nevermind|stop(?: this action)?|(?:yes, )?(?:don't|do not|never) (?:release|hold|reset)(?: anything| this payment| the demo)?)"))return yes('Cancel this action');
 const reason=t.match(/^(?:reason\s*[:=-]\s*|because |my reason is |justification\s*[:=-]\s*)(.+)$/);
 if(reason)return financialReason(reason[1])?yes('Reason: '+reason[1]):deny;
 const action=t.match(new RegExp(`^(release|hold|freeze|unhold|approve the release of|pause|put|place) ((?:this|that|the|current|selected) payment|it|${ref}|${supplier}|all payments)(?: on hold)?(?: because (.+))?$`));
 if(action){if(action[3]&&!financialReason(action[3]))return deny;const verb=['release','unhold','approve the release of'].includes(action[1])?'release':'hold';return yes(`${verb} ${action[2]}${action[3]?' because '+action[3]:''}`);}
 if(exact(t,`(?:request (?:further |human )?verification|escalate(?: this case| the case)?|request human review|ask a human|verify with the supplier)${caseSuffix}`))return yes(t);
 if(exact(t,`${request} (?:a |the |my |simple )?(?:simple )?(?:overview|workspace overview|financial overview|summary|dashboard|payment status|exposure|risk summary)(?: of (?:my |the )?workspace)?`))return yes('Give me an overview');
 if(exact(t,'(?:what needs attention|how many payments are (?:held|queued)|how much (?:exposure|risk) is under review)'))return yes('Give me an overview');
 if(exact(t,`${request} (?:the |my |previous )?(?:investigations|cases|case history|previous investigations)`))return yes('Show my investigations');
 if(exact(t,`${request} ${ref}`))return yes(t);
 const paymentPattern=`${request} (?:the |my |all )?(?:(?:queued|pending|held|blocked|released) )?(?:payments|transactions|payment queue)(?: (?:for|from) ${supplier})?(?: (?:above|over|more than|greater than) (?:rs\\.? |inr |₹)?[\\d,.]+(?: (?:lakh|lac|crore|k|million))?)?`;
 if(exact(t,paymentPattern)||exact(t,`${request} ${supplier}(?: payments)?`))return yes(t);
 if(exact(t,'(?:next|more|show more|next page|show (?:the )?next(?: 20)?(?: payments)?)'))return yes('Show the next 20 payments');
 if(exact(t,`${request} (?:the |this |my )?(?:evidence graph|graph|provenance|source chain|shared origin|common origin)${caseSuffix}`))return yes(t);
 if(exact(t,`${request} (?:the |this |my )?(?:signed |independent |source )?(?:evidence|contract|invoice|documents|sources|proof|confirmation)${caseSuffix}`))return yes(t);
 if(exact(t,`${request} (?:the |this |my |an? )?(?:audit |investigation )?(?:report|audit trail|audit history)(?: (?:as|in) (?:pdf|json))?${caseSuffix}`)||exact(t,`(?:export|download) (?:the )?(?:audit |investigation )?report(?: (?:as|in) (?:pdf|json))?${caseSuffix}`))return yes(t);
 if(exact(t,`${request} (?:the )?(?:agents|agent activity|tool calls|receipts|execution|timeline)${caseSuffix}`))return yes(t);
 if(exact(t,`${request} (?:the )?(?:action policy|policy|permissions|authorization rules|payment controls)`))return yes(t);
 if(exact(t,`${request} (?:the )?(?:hypotheses|possible explanations|alternative explanations|uncertainty|decision details)${caseSuffix}`)||exact(t,`what are the possible explanations${caseSuffix}`))return yes('Explain possible explanations'+(t.match(/ (?:for|of|in|about) (?:ts|pay)[- ]?\d+$/)?.[0]||''));
 if(exact(t,'(?:run|start|measure|test)(?: the)? (?:evaluation|benchmark)(?: again)?|compare approaches|test the system'))return yes('Run the evaluation');
 if(exact(t,`${request} (?:the |latest )?(?:evaluation|benchmark|performance|accuracy|recall|false positives|evaluation results)`))return yes('Show evaluation');
 if(exact(t,'(?:explain (?:that|this|it|the result|the results|those results|the report|the investigation result)(?: in simple words| simply)?|why (?:was|is) (?:it|this payment|the payment) (?:held|blocked)|why was this decision made|what happened|what did you find|is (?:it|this) fraud|what should i do(?: next)?|next steps|what now|show the investigation result)'))return yes(t);
 if(exact(t,`${request} (?:the |this )?(?:result|finding)${caseSuffix}`))return yes('Explain the result'+(t.match(/ (?:for|of|in|about) (?:ts|pay)[- ]?\d+$/)?.[0]||''));
 if(exact(t,'(?:which integrations are connected|what integrations are connected|show (?:the )?(?:environment status|connections|settings)|is (?:gemini|google cloud|chatgpt) connected)'))return yes('Which integrations are connected?');
 if(exact(t,'(?:download (?:the )?(?:project|source code|zip)|show (?:the )?project files|give me (?:the )?source code)'))return yes('Download the project');
 if(exact(t,'(?:explain how to run (?:it|truestate) locally|how do i run truestate locally|show (?:the )?local setup)'))return yes('Explain how to run it locally');
 if(exact(t,"(?:help|what can i ask(?: you to do)?|what can you do|show me what i can do|how does (?:truestate|this) work|explain how (?:truestate|this) works|how does truestate (?:find hidden risk|detect risk)|what is truestate|what's truestate)"))return yes('Explain how TRUESTATE works');
 return deny;
}
