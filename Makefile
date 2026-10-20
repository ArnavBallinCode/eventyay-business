all: localecompile
LNGS:=$(shell find eventyay_business/locale -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sed 's/^/-l /')

localecompile:
	django-admin compilemessages

localegen:
	django-admin makemessages --add-location file --keep-pot -i build -i dist -i "*egg*" $(LNGS)

.PHONY: all localecompile localegen
