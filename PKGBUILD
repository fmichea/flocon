# Maintainer: Franck Michea <franck.michea@gmail.com>
# Maintainer: Yannick LM <yannicklm1337@gmail.com>
pkgname=flocon-git
pkgver=20121105
pkgrel=1
pkgdesc=""
arch=('i686' 'x86_64')
url=""
license=()
groups=()
depends=('python2' 'twisted')
makedepends=()
optdepends=()
provides=()
conflicts=()
replaces=()
backup=()
options=()
install=
changelog=
source=()
noextract=()
md5sums=()

_gitroot='https://bitbucket.org/kushou/flocon.git'
_gitname='flocon'

build() {
    if [ -d "$_gitname" ]; then
        cd "$_gitname"
        git checkout master
        git pull --rebase
    else
        git clone "$_gitroot" "$_gitname"
        cd "$_gitname"
    fi

    python2 setup.py build
}

package() {
    cd "$_gitname"

    python2 setup.py install --root=$pkgdir/ --optimize=1
}
