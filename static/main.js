function disableEmpty(form) {
  var elements = form.elements;
  for (var i = 0; i < elements.length; i++) {
    elements[i].disabled = elements[i].value == '';
  }
}
