sphinx-apidoc -f -o ./docs ./pyopenlab
cd docs
make html
make latexpdf
