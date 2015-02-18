# ...

.PHONY: default help
default: pre-commit
help:
	@echo 'make post-checkout|pre-commit'
	@echo 'make check|clean|doc|help'
	@echo 'make pofiles|mofiles'


.PHONY: htmlindent pepclean flake8 vimmodelines
htmlindent:
	find . -name '*.html' | while read n; do \
	  min=0; \
	  sed -e 's/^\( *\).*/\1/;/^$$/d' < "$$n" | \
	  sort -u | \
	  while IFS= read l; do \
	    test $$min -eq 0 && test $${#l} -ne 4 && echo "indent: $$n (offset $${#l} is not 4)" && break; \
	    min=1; \
	    test $$(($${#l} % 4)) -ne 0 && echo "indent: $$n (indent $${#l} is not 4)" && break; \
	  done; true; \
	done
pepclean:
	@# Replace tabs with spaces, remove trailing spaces, remove trailing newlines.
	which pepclean >/dev/null && \
	  find . '(' -name '*.py' -o -name '*.html' -o -name '*.xml' ')' \
	    -type f -print0 | xargs --no-run-if-empty -0 pepclean
flake8: pepclean vimmodelines
	@# Use a custom --format so the path is space separated for
	@# easier copy-pasting.
	-find . -name '*.py' '!' -name 'argparse_1_2_1.py' -print0 | \
	  xargs --no-run-if-empty -0 flake8 \
	    --max-line-length=79 --max-complexity=10 \
	    --format='%(path)s %(row)d:%(col)d [%(code)s] %(text)s'
vimmodelines:
	find . -name '*.py' '!' -name 'argparse_1_2_1.py' -size +0 \
	    '!' -perm -u=x -print0 | \
	  xargs --no-run-if-empty -0 grep -L '^# vim:' | \
	  xargs --no-run-if-empty -d\\n \
	    sed -i -e '1i# vim: set ts=8 sw=4 sts=4 et ai tw=79:'


# Run me before committing.
.PHONY: pre-commit
# ... disabled: doc mofiles
pre-commit: htmlindent pepclean flake8 vimmodelines
