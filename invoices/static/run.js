/* Shivving (IE8 is not supported, but at least it won't look as awful)
/* ========================================================================== */

(function (document) {
	var
	head = document.head = document.getElementsByTagName('head')[0] || document.documentElement,
	elements = 'article aside audio bdi canvas data datalist details figcaption figure footer header hgroup mark meter nav output picture progress section summary time video x'.split(' '),
	elementsLength = elements.length,
	elementsIndex = 0,
	element;

	while (elementsIndex < elementsLength) {
		element = document.createElement(elements[++elementsIndex]);
	}

	element.innerHTML = 'x<style>' +
		'article,aside,details,figcaption,figure,footer,header,hgroup,nav,section{display:block}' +
		'audio[controls],canvas,video{display:inline-block}' +
		'[hidden],audio{display:none}' +
		'mark{background:#FF0;color:#000}' +
	'</style>';

	return head.insertBefore(element.lastChild, head.firstChild);
})(document);

/* Prototyping
/* ========================================================================== */

(function (window, ElementPrototype, ArrayPrototype, polyfill) {
	function NodeList() { [polyfill] }
	NodeList.prototype.length = ArrayPrototype.length;

	ElementPrototype.matchesSelector = ElementPrototype.matchesSelector ||
	ElementPrototype.mozMatchesSelector ||
	ElementPrototype.msMatchesSelector ||
	ElementPrototype.oMatchesSelector ||
	ElementPrototype.webkitMatchesSelector ||
	function matchesSelector(selector) {
		return ArrayPrototype.indexOf.call(this.parentNode.querySelectorAll(selector), this) > -1;
	};

	ElementPrototype.ancestorQuerySelectorAll = ElementPrototype.ancestorQuerySelectorAll ||
	ElementPrototype.mozAncestorQuerySelectorAll ||
	ElementPrototype.msAncestorQuerySelectorAll ||
	ElementPrototype.oAncestorQuerySelectorAll ||
	ElementPrototype.webkitAncestorQuerySelectorAll ||
	function ancestorQuerySelectorAll(selector) {
		for (var cite = this, newNodeList = new NodeList; cite = cite.parentElement;) {
			if (cite.matchesSelector(selector)) ArrayPrototype.push.call(newNodeList, cite);
		}

		return newNodeList;
	};

	ElementPrototype.ancestorQuerySelector = ElementPrototype.ancestorQuerySelector ||
	ElementPrototype.mozAncestorQuerySelector ||
	ElementPrototype.msAncestorQuerySelector ||
	ElementPrototype.oAncestorQuerySelector ||
	ElementPrototype.webkitAncestorQuerySelector ||
	function ancestorQuerySelector(selector) {
		return this.ancestorQuerySelectorAll(selector)[0] || null;
	};
})(this, Element.prototype, Array.prototype);

/* Helper Functions
/* ========================================================================== */

function generateTableRow() {
	var emptyColumn = document.createElement('tr');

	emptyColumn.innerHTML = '<td><a class="cut">-</a><span contenteditable></span></td>' +
		'<td class="right"><span contenteditable></span></td>' +
    '<td class="right"><span contenteditable></span></td>' +
    '<td class="right"><span contenteditable></span></td>' +
    '<td class="right"><span contenteditable></span></td>' +
	'<td class="right"><span contenteditable></span></td>' +
	'<td class="right"><span contenteditable></span></td>' +
    '<td class="right"><span contenteditable></span></td>' +
		'<td class="right"><span data-prefix>रु</span><span contenteditable>0.00</span></td>' +
		'<td class="right"><span contenteditable>1</span></td>' +
		'<td class="right"><span data-prefix>रु</span><span>0.00</span></td>' +
    '<td class="center"><span contenteditable>x</span></td>' +
    '<td class="center"><span contenteditable></span></td>' +
		'<td width="0" style="visibility:collapse;"><span></span></td>'
    ;


	return emptyColumn;
}

function parseFloatHTML(element) {
	try{
		var val = parseFloat(element.innerHTML.replace(/[^\d\.\-]+/g, '')) || 0;
	}catch(err){
		// debugger;
		return 0;
	}
	return val;
}

function parsePrice(number) {
	return number.toFixed(2).replace(/(\d)(?=(\d\d\d)+([^\d]|रु))/g, '$1,');
}

/* Update Number
/* ========================================================================== */

function updateNumber(e) {
	var
	activeElement = document.activeElement,
	value = parseFloat(activeElement.innerHTML),
	wasPrice = activeElement.innerHTML == parsePrice(parseFloatHTML(activeElement));

	if (!isNaN(value) && (e.keyCode == 38 || e.keyCode == 40 || e.wheelDeltaY)) {
		e.preventDefault();

		value += e.keyCode == 38 ? 1 : e.keyCode == 40 ? -1 : Math.round(e.wheelDelta * 0.025);
		value = Math.max(value, 0);

		activeElement.innerHTML = wasPrice ? parsePrice(value) : value;
	}

	updateInvoice();
}

/* Update Invoice
/* ========================================================================== */

function updateInvoice() {
	var due_prev = parseFloatHTML(document.querySelector('table.meta tr:last-child td:last-child span:last-child'));
	var items_obj = [];
	var invoice = {};
	var total = 0;
	var taxable = 0;
	var cells, price, total, a, i;

	// update inventory cells
	// ======================

	for (var a = document.querySelectorAll('table.inventory tbody tr'), i = 0; a[i]; ++i) {
		// get inventory row cells
		cells = a[i].querySelectorAll('span:last-child');
    cells[0].innerHTML = i + 1;
    var price_sub = 0;
		// set price as cell[2] * cell[3]
    mm = //parseFloatHTML(cells[1]) *
		parseFloatHTML(cells[2])
     * parseFloatHTML(cells[3])
     * parseFloatHTML(cells[4])/2592
	
	if (mm === 0){
		if (parseFloatHTML(cells[5]) != 0){
			mm = parseFloatHTML(cells[5]);
		}
	}
	
	j=1;

	if (mm !== 0 ){
		if (mm !== parseFloatHTML(cells[5])){ // To handle manual insertion in MM
			cells[5].innerText = mm.toFixed(0);
		}
		
		
		cells[6 + j].innerText = mm.toFixed(2) + ' mm';
	}
	

	price_sub = mm * parseFloatHTML(cells[5 + j])

    if (price_sub > 0){
      cells[7 + j].innerText = price_sub.toFixed(2);
    } else{
      price_sub = parseFloatHTML(cells[7 + j])
    }
		price = price_sub * parseFloatHTML(cells[8 + j]);
		// add price to total
		total += price;
    if (cells[10 + j].innerText.toUpperCase() == 'X'){
      console.log(price,taxable);
      if (cells[11 + j].innerText.toUpperCase() == "X"){
        tax = price / 1.13 * .13;
        taxable += tax;
				total += -tax;
        if (price != 0){
            price += -tax;
        }
      } else{
        taxable += price * .13;
      }
    }
		// set row total
		cells[9 + j].innerText = price.toFixed(2);
		items_obj.push(
			{
				"density": cells[1].innerHTML.toUpperCase(),
				"length": parseFloatHTML(cells[2]),
				"breadth": parseFloatHTML(cells[3]),
				"height": parseFloatHTML(cells[4]),
				"mm":  parseFloatHTML(cells[5]),
				"rate":  parseFloatHTML(cells[6]),
				"description":  cells[7].innerText,
				"calculated_rate":  parseFloatHTML(cells[8]),
				"qty":  parseFloatHTML(cells[9]),
				"price":  parseFloatHTML(cells[10]),
				"taxable":  cells[11].innerText.toUpperCase() === "X",
				"tax_include":  cells[12].innerText.toUpperCase() ==="X",
				"id": cells[13].innerHTML
			}
		)
	}

	// update balance cells
	// ====================

	// get balance cells
	cells = document.querySelectorAll('table.balance td:last-child span:last-child');

	// set total
	cells[0].innerText = total;
	cells[2].innerText = taxable;
	// set balance and meta balance
	cells[3].innerText = parsePrice(total - parseFloatHTML(cells[1]) + taxable);
	cells[5].innerText = parseFloatHTML(cells[3]) - parseFloatHTML(cells[4])
	
	// update objects
	invoice['total'] = parseFloatHTML(cells[3])
	invoice['paid'] = parseFloatHTML(cells[1])
	invoice['tax'] = taxable
	invoice['discount'] = parseFloatHTML(cells[4])
	invoice['to_pay'] = invoice['total'] - invoice['paid'] - invoice['discount']
	console.log(items_obj, invoice)
	document.getElementById('invoice').value = JSON.stringify(invoice);
	document.getElementById('items').value = JSON.stringify(items_obj);
	
	// update prefix formatting
	// ========================

	var prefix = document.querySelector('#prefix').innerHTML;
	for (a = document.querySelectorAll('[data-prefix]'), i = 0; a[i]; ++i) a[i].innerHTML = prefix;

	// update price formatting
	// =======================

	for (a = document.querySelectorAll('span[data-prefix] + span'), i = 0; a[i]; ++i) if (document.activeElement != a[i]) a[i].innerHTML = parsePrice(parseFloatHTML(a[i]));
}

/* On Content Load
/* ========================================================================== */

function onContentLoad() {
	updateInvoice();

	var
	input = document.querySelector('input'),
	image = document.querySelector('img');

	function onClick(e) {
		var element = e.target.querySelector('[contenteditable]'), row;

		element && e.target != document.documentElement && e.target != document.body && element.focus();

		if (e.target.matchesSelector('.add')) {
			document.querySelector('table.inventory tbody').appendChild(generateTableRow());
		}
		else if (e.target.className == 'cut') {
			row = e.target.ancestorQuerySelector('tr');

			row.parentNode.removeChild(row);
		}

		updateInvoice();
	}

	function onEnterCancel(e) {
		e.preventDefault();

		image.classList.add('hover');
	}

	function onLeaveCancel(e) {
		e.preventDefault();

		image.classList.remove('hover');
	}

	function onFileInput(e) {
		image.classList.remove('hover');

		var
		reader = new FileReader(),
		files = e.dataTransfer ? e.dataTransfer.files : e.target.files,
		i = 0;

		reader.onload = onFileLoad;

		while (files[i]) reader.readAsDataURL(files[i++]);
	}

	function onFileLoad(e) {
		var data = e.target.result;

		image.src = data;
	}

	if (window.addEventListener) {
		document.addEventListener('click', onClick);

		document.addEventListener('mousewheel', updateNumber);
		document.addEventListener('keydown', updateNumber);

		document.addEventListener('keydown', updateInvoice);
		document.addEventListener('keyup', updateInvoice);

		input.addEventListener('focus', onEnterCancel);
		input.addEventListener('mouseover', onEnterCancel);
		input.addEventListener('dragover', onEnterCancel);
		input.addEventListener('dragenter', onEnterCancel);

		input.addEventListener('blur', onLeaveCancel);
		input.addEventListener('dragleave', onLeaveCancel);
		input.addEventListener('mouseout', onLeaveCancel);

		input.addEventListener('drop', onFileInput);
		input.addEventListener('change', onFileInput);
	}
}

window.addEventListener && document.addEventListener('DOMContentLoaded', onContentLoad);
