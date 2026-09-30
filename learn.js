const slug = location.pathname.split('/').filter(Boolean)[1];
const guide = slug ? signalGuides[slug] : null;

if (guide) {
  document.title = guide.title + ' — Candlepoint';
  document.querySelector('#guide-crumb').hidden = false;
  document.querySelector('#guide-separator').hidden = false;
  document.querySelector('#current-crumb').textContent = guide.title;
  document.querySelector('#category').textContent = guide.category;
  document.querySelector('#page-title').textContent = guide.title;
  document.querySelector('#intro').textContent = guide.summary;
  document.querySelector('#meaning').textContent = guide.meaning;
  document.querySelector('#checks').replaceChildren(...guide.checks.map(check => {
    const item = document.createElement('li'); item.textContent = check; return item;
  }));
  document.querySelector('#example').textContent = guide.example;
  document.querySelector('#note').textContent = guide.note;
  document.querySelector('#detail').hidden = false;
  document.querySelector('#guide-list').hidden = true;
  document.querySelector('#more').hidden = false;
} else {
  const cards = Object.entries(signalGuides).map(([key, item]) => {
    const link = document.createElement('a');
    link.className = 'card guide-link';
    link.href = '/learn/' + key;
    for (const [tag, content] of [['span', item.category], ['strong', item.title], ['p', item.summary]]) {
      const child = document.createElement(tag); child.textContent = content; link.append(child);
    }
    return link;
  });
  document.querySelector('#guide-list').replaceChildren(...cards);
}
