(function(){
  var bar=document.getElementById('faBar'), article=document.getElementById('faArticle'), hdr=document.querySelector('.header'), root=document.querySelector('.fa');
  function setHdr(){root.style.setProperty('--fa-hdr',(hdr?hdr.offsetHeight:0)+'px');}
  setHdr();window.addEventListener('resize',setHdr);

  // HUD: шаги-уровни
  var links=[].slice.call(document.querySelectorAll('#faHud a'));
  var secs=[].slice.call(article.querySelectorAll('section[data-step]'));
  function tick(){
    var h=document.documentElement, max=h.scrollHeight-window.innerHeight;
    bar.style.width=(max>0?Math.min(100,Math.max(0,window.scrollY/max*100)):0)+'%';
    var line=window.innerHeight*0.4, cur=0;
    secs.forEach(function(s){ if(s.getBoundingClientRect().top<line) cur=+s.getAttribute('data-step'); });
    links.forEach(function(a){
      var n=+a.getAttribute('data-step'), li=a.parentNode;
      li.classList.toggle('fa-is-done',n<cur);
      li.classList.toggle('fa-is-active',n===cur);
      a.classList.toggle('fa-is-active',n===cur);
      a.classList.toggle('fa-is-done',n<cur);
      if(n===cur)a.setAttribute('aria-current','step');else a.removeAttribute('aria-current');
    });
  }
  window.addEventListener('scroll',tick,{passive:true});window.addEventListener('resize',tick);tick();

  // Трекер (в памяти)
  var grid=document.getElementById('trackerGrid'), cnt=document.getElementById('trackerCount'), tb=document.getElementById('trackerBar'), tm=document.getElementById('trackerMsg');
  var state=[];
  function texts(n){
    if(n===0) return 'Нажимай на дни, когда решил задачу.';
    if(n<7) return 'Старт дан. Первая неделя самая трудная.';
    if(n<15) return 'Ритм появился. Держи темп.';
    if(n<30) return 'Ты уже дальше, чем Макс в октябре.';
    return 'Квест пройден. Пора на настоящую олимпиаду.';
  }
  function render(){var n=state.filter(Boolean).length;cnt.textContent=n+' из 30';tb.style.width=(n/30*100)+'%';tm.textContent=texts(n);}
  for(var i=0;i<30;i++){
    (function(i){
      var b=document.createElement('button');b.type='button';b.className='fa-day';b.textContent=i+1;
      b.setAttribute('aria-pressed','false');b.setAttribute('aria-label','День '+(i+1));
      b.addEventListener('click',function(){state[i]=!state[i];b.setAttribute('aria-pressed',state[i]?'true':'false');render();});
      grid.appendChild(b);
    })(i);
  }
  render();
})();
