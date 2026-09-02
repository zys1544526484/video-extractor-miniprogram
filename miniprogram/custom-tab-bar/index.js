Component({
  data: {
    selected: 0,
    list: [
      {
        pagePath: '/pages/index/index',
        text: '首页',
        iconPath: '/assets/icons/home.svg',
        selectedIconPath: '/assets/icons/home-active.svg'
      },
      {
        pagePath: '/pages/mine/mine',
        text: '我的',
        iconPath: '/assets/icons/user.svg',
        selectedIconPath: '/assets/icons/user-active.svg'
      }
    ]
  },

  lifetimes: {
    attached() {
      this.syncSelected()
    }
  },

  pageLifetimes: {
    show() {
      this.syncSelected()
    }
  },

  methods: {
    syncSelected() {
      const pages = getCurrentPages()
      const route = pages.length ? `/${pages[pages.length - 1].route}` : ''
      const index = this.data.list.findIndex((item) => item.pagePath === route)
      if (index >= 0 && index !== this.data.selected) this.setData({ selected: index })
    },

    switchTab(event) {
      const { path, index } = event.currentTarget.dataset
      if (index === this.data.selected) return
      wx.switchTab({ url: path })
    }
  }
})

