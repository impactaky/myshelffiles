export GH_TOKEN="op://shelffiles/GH_TOKEN/credential"
alias gh="op run --no-masking -- gh"

function atuin_login() {
  ATUIN_USER="op://shelffiles/atuin/username" \
  ATUIN_PASSWORD="op://shelffiles/atuin/password" \
  ATUIN_KEY="op://shelffiles/atuin_key/password" \
  op run --no-masking -- zsh -c '''
    atuin login \
      --username "$ATUIN_USER" \
      --password "$ATUIN_PASSWORD" \
      --key "$ATUIN_KEY"
    '''
}
