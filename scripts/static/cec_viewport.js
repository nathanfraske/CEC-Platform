/* Shared, dependency-free precision-trackpad interaction for PCB review. */
(function (root) {
  'use strict';
  function clamp(value, low, high) { return Math.min(high, Math.max(low, value)); }
  function wheel(event, width, height, wheelZoom) {
    const units = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? height : 1;
    const dx = Number(event.deltaX || 0) * units;
    const dy = Number(event.deltaY || 0) * units;
    const zoom = Boolean(event.ctrlKey || event.metaKey || event.altKey || wheelZoom);
    return {zoom, dx, dy, factor: zoom ? Math.exp(-clamp(dy, -300, 300) * 0.008) : 1};
  }
  function zoomBox(box, factor, point, limits) {
    const w = clamp(box.w / factor, limits.min, limits.max);
    const ratio = w / box.w;
    return {x: point.x - (point.x - box.x) * ratio,
            y: point.y - (point.y - box.y) * ratio, w, h: box.h * ratio};
  }
  function bind(element, options) {
    let drag = null;
    function point(event) {
      const r = element.getBoundingClientRect(), b = options.read();
      return {x: b.x + (event.clientX-r.left)/r.width*b.w,
              y: b.y + (event.clientY-r.top)/r.height*b.h};
    }
    element.addEventListener('wheel', event => {
      event.preventDefault();
      const r=element.getBoundingClientRect(), b=options.read();
      const action=wheel(event,r.width,r.height,options.wheelZoom && options.wheelZoom());
      if(action.zoom) options.write(zoomBox(b,action.factor,point(event),options.limits));
      else options.write({...b,x:b.x+action.dx*b.w/r.width,y:b.y+action.dy*b.h/r.height});
    }, {passive:false});
    element.addEventListener('pointerdown', event => {
      if(event.button!==0 || event.isPrimary===false) return;
      const r=element.getBoundingClientRect();
      drag={x:event.clientX,y:event.clientY,box:{...options.read()},width:r.width,height:r.height,moved:false};
      element.setPointerCapture(event.pointerId);
      element.focus({preventScroll:true});
    });
    element.addEventListener('pointermove', event => {
      if(options.hover) options.hover(point(event));
      if(!drag) return;
      const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
      if(Math.hypot(dx,dy)>4) drag.moved=true;
      options.write({...drag.box,x:drag.box.x-dx*drag.box.w/drag.width,
                     y:drag.box.y-dy*drag.box.h/drag.height});
    });
    element.addEventListener('pointerup', event => {
      if(!drag) return;
      const click=!drag.moved;drag=null;
      if(element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
      if(click && options.click) options.click(point(event),event);
    });
    element.addEventListener('pointercancel',()=>{drag=null;});
    element.addEventListener('dblclick',event=>{
      event.preventDefault();options.write(zoomBox(options.read(),2,point(event),options.limits));
    });
    element.addEventListener('keydown',event=>{
      if(event.ctrlKey||event.metaKey||event.altKey) return;
      const b=options.read();let changed=true;
      if(event.key==='+'||event.key==='='||event.key==='-') {
        options.write(zoomBox(b,event.key==='-'?0.8:1.25,{x:b.x+b.w/2,y:b.y+b.h/2},options.limits));
      } else if(event.key.toLowerCase()==='f'||event.key==='Home') options.fit();
      else if(event.key==='ArrowLeft') options.write({...b,x:b.x-b.w*.1});
      else if(event.key==='ArrowRight') options.write({...b,x:b.x+b.w*.1});
      else if(event.key==='ArrowUp') options.write({...b,y:b.y-b.h*.1});
      else if(event.key==='ArrowDown') options.write({...b,y:b.y+b.h*.1});
      else changed=false;
      if(changed) event.preventDefault();
    });
    return {point};
  }
  root.CECViewport={clamp,wheel,zoomBox,bind};
  if(typeof module!=='undefined' && module.exports) module.exports=root.CECViewport;
})(typeof globalThis!=='undefined'?globalThis:this);
