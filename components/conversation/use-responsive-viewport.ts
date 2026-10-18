'use client';
import {useEffect} from 'react';

/** Keep the chat within the visible viewport when mobile browser chrome or a keyboard moves. */
export function useResponsiveViewport(){
 useEffect(()=>{
  const root=document.documentElement;
  const viewport=window.visualViewport;
  let frame=0;
  function measure(){
   cancelAnimationFrame(frame);
   frame=requestAnimationFrame(()=>{
    // Pinch zoom must remain a browser operation, without resizing the application underneath it.
    if(viewport&&Math.abs(viewport.scale-1)>.01)return;
    const height=viewport?.height||window.innerHeight;
    root.style.setProperty('--app-height',`${Math.round(height)}px`);
    root.style.setProperty('--app-top',`${Math.round(viewport?.offsetTop||0)}px`);
    root.dataset.shortViewport=height<500?'true':'false';
   });
  }
  measure();
  window.addEventListener('resize',measure);
  viewport?.addEventListener('resize',measure);
  viewport?.addEventListener('scroll',measure);
  return()=>{
   cancelAnimationFrame(frame);
   window.removeEventListener('resize',measure);
   viewport?.removeEventListener('resize',measure);
   viewport?.removeEventListener('scroll',measure);
   root.style.removeProperty('--app-height');root.style.removeProperty('--app-top');
   delete root.dataset.shortViewport;
  };
 },[]);
}
