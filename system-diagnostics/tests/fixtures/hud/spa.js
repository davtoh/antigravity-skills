var app = document.getElementById('app');
function render(path) {
  app.innerHTML = '<ul><li><a href="#">one</a></li><li><button class="go">go ' + path + '</button></li></ul>';
  app.querySelector('.go').onclick = function () { history.pushState({}, '', '/spa-next'); fetch('/api/ping?route=1'); };
}
render('/spa.html');
