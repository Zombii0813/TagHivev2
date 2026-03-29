<template>
  <div class="tag-panel" @dragover="handlePanelDragOver">
    <div class="panel-header">
      <h3>标签</h3>
      <el-button
        type="primary"
        size="small"
        :icon="Plus"
        @click="showCreateDialog = true"
      >
        新建
      </el-button>
    </div>

    <!-- 过滤状态提示 -->
    <div class="filter-status" :class="{ active: tagStore.hasSelection }">
      <el-alert
        :title="tagStore.hasSelection ? `已选择 ${tagStore.selectedTagIds.size} 个标签过滤` : '点击标签进行过滤'"
        :type="tagStore.hasSelection ? 'info' : 'info'"
        :closable="false"
        show-icon
      >
        <template #default>
          <el-button
            v-if="tagStore.hasSelection"
            type="primary"
            link
            size="small"
            :icon="Close"
            @click="clearFilter"
          >
            清除过滤
          </el-button>
          <span v-else class="filter-hint">支持多选 (Ctrl+点击)</span>
        </template>
      </el-alert>
    </div>

    <div
      ref="tagListRef"
      class="tag-list"
      :class="{ 'list-drop-active': listDropActive }"
      v-loading="tagStore.isLoading"
      @dragover.prevent="handleTagListDragOver"
      @dragleave="handleTagListDragLeave"
      @drop.prevent="handleTagListDrop"
    >
      <div
        v-for="tag in tagStore.orderedTags"
        :key="tag.id"
        class="tag-item"
        :class="{
          selected: tagStore.selectedTagIds.has(tag.id),
          'drag-source': draggingTagId === tag.id,
          'drag-over': reorderTargetTagId === tag.id,
        }"
        :style="{ backgroundColor: tag.color + '20', borderColor: tag.color }"
        :data-tag-id="tag.id"
        draggable="true"
        @click="handleTagClick(tag.id, $event)"
        @contextmenu.prevent="handleContextMenu(tag, $event)"
        @dragstart="handleTagDragStart(tag.id, $event)"
        @dragend="resetDragState"
        @dragover.prevent.stop="handleTagDragOver(tag.id, $event)"
        @dragleave="handleTagDragLeave(tag.id)"
        @drop.prevent.stop="handleTagDrop(tag, $event)"
      >
        <span v-if="tag.icon" class="tag-icon">{{ tag.icon }}</span>
        <span v-else class="tag-dot" :style="{ backgroundColor: tag.color }"></span>
        <span class="tag-name">{{ tag.name }}</span>
        <span class="tag-count">{{ tag.file_count }}</span>
      </div>
    </div>

    <!-- 新建标签对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="新建标签"
      width="420px"
      append-to-body
      :modal-class="'tag-dialog-modal'"
      @open="emojiPickerVisible = false; removeEmojiPickerCloseHandler()"
    >
      <!-- 图标选择器（顶部居中） -->
      <div class="dialog-icon-section">
        <div
          ref="createIconBtnRef"
          class="dialog-icon-btn"
          :style="newTag.icon ? { borderColor: newTag.color, background: newTag.color + '18' } : { borderColor: newTag.color }"
          @click="toggleEmojiPicker('create')"
        >
          <span v-if="newTag.icon" class="dialog-icon-emoji">{{ newTag.icon }}</span>
          <span v-else class="dialog-icon-dot" :style="{ backgroundColor: newTag.color }"></span>
          <span class="dialog-icon-hint">点击选择图标</span>
        </div>
        <span v-if="newTag.icon" class="dialog-icon-clear" @click.stop="newTag.icon = ''">移除图标</span>
      </div>

      <el-form :model="newTag" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="newTag.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="newTag.color" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="newTag.description"
            type="textarea"
            placeholder="可选描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createTag">确定</el-button>
      </template>
    </el-dialog>

    <!-- 标签右键菜单 -->
    <el-popover
      :visible="contextMenuVisible"
      :virtual-ref="contextMenuTrigger"
      virtual-triggering
      trigger="contextmenu"
      placement="bottom-start"
      :width="140"
      popper-class="context-menu-popover"
      @update:visible="onContextMenuVisibleChange"
    >
      <div class="context-menu">
        <div class="context-menu-item" @click="editTag">
          <el-icon><Edit /></el-icon>
          <span>编辑标签</span>
        </div>
        <div class="context-menu-item delete" @click="confirmDeleteTag">
          <el-icon><Delete /></el-icon>
          <span>删除标签</span>
        </div>
      </div>
    </el-popover>

    <!-- 编辑标签对话框 -->
    <el-dialog
      v-model="showEditDialog"
      title="编辑标签"
      width="420px"
      append-to-body
      :modal-class="'tag-dialog-modal'"
      @open="emojiPickerVisible = false; removeEmojiPickerCloseHandler()"
    >
      <!-- 图标选择器（顶部居中） -->
      <div class="dialog-icon-section">
        <div
          ref="editIconBtnRef"
          class="dialog-icon-btn"
          :style="editingTag.icon ? { borderColor: editingTag.color, background: editingTag.color + '18' } : { borderColor: editingTag.color }"
          @click="toggleEmojiPicker('edit')"
        >
          <span v-if="editingTag.icon" class="dialog-icon-emoji">{{ editingTag.icon }}</span>
          <span v-else class="dialog-icon-dot" :style="{ backgroundColor: editingTag.color }"></span>
          <span class="dialog-icon-hint">点击选择图标</span>
        </div>
        <span v-if="editingTag.icon" class="dialog-icon-clear" @click.stop="editingTag.icon = ''">移除图标</span>
      </div>

      <el-form :model="editingTag" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="editingTag.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="editingTag.color" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="editingTag.description"
            type="textarea"
            placeholder="可选描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTagEdit">确定</el-button>
      </template>
    </el-dialog>

    <!-- Emoji 选择器弹出层 -->
    <teleport to="body">
      <div
        v-if="emojiPickerVisible"
        class="emoji-picker-popup"
        :style="emojiPickerStyle"
        @click.stop
      >
          <div class="emoji-picker-tabs">
            <span
              v-for="cat in emojiCategories"
              :key="cat.name"
              class="emoji-picker-tab"
              :class="{ active: activeEmojiCategory === cat.name }"
              :title="cat.label"
              @click="activeEmojiCategory = cat.name"
            >{{ cat.icon }}</span>
          </div>
          <div class="emoji-picker-grid">
            <span
              v-for="e in currentCategoryEmojis"
              :key="e"
              class="emoji-picker-item"
              :class="{ active: currentIcon === e }"
              @click="selectEmoji(e)"
            >{{ e }}</span>
          </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Plus, Close, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTagStore } from '../stores/tags'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'
import type { Tag } from '../types'
import { getDraggedTagId, setTagDragData, hasTagDrag, clearTagDragState, isTagDragInProgress } from '../utils/drag'

const tagStore = useTagStore()
const fileStore = useFileStore()
const appStore = useAppStore()

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const newTag = ref({
  name: '',
  color: '#409EFF',
  icon: '',
  description: '',
})

const editingTag = ref<Tag & { description?: string }>({
  id: 0,
  name: '',
  color: '#409EFF',
  icon: '',
  description: '',
  created_at: '',
  file_count: 0,
})

// Emoji 选择器状态
const emojiPickerVisible = ref(false)
const emojiPickerTarget = ref<'create' | 'edit'>('create')
const emojiPickerStyle = ref<Record<string, string>>({})
const activeEmojiCategory = ref('smileys')
const createIconBtnRef = ref<HTMLElement | null>(null)
const editIconBtnRef = ref<HTMLElement | null>(null)

const currentIcon = computed(() =>
  emojiPickerTarget.value === 'create' ? newTag.value.icon : editingTag.value.icon
)

// 完整 emoji 数据（按分类）
const emojiCategories = [
  { name: 'smileys', label: '笑脸与情感', icon: '😀' },
  { name: 'people', label: '人物', icon: '👤' },
  { name: 'animals', label: '动物与自然', icon: '🐶' },
  { name: 'food', label: '食物与饮料', icon: '🍎' },
  { name: 'travel', label: '旅行与地点', icon: '✈️' },
  { name: 'activities', label: '活动', icon: '⚽' },
  { name: 'objects', label: '物品', icon: '💡' },
  { name: 'symbols', label: '符号', icon: '❤️' },
  { name: 'flags', label: '旗帜', icon: '🚩' },
]

const emojiData: Record<string, string[]> = {
  smileys: [
    '😀','😃','😄','😁','😆','😅','🤣','😂','🙂','🙃','🫠','😉','😊','😇','🥰','😍','🤩','😘','😗','☺️',
    '😚','😙','🥲','😋','😛','😜','🤪','😝','🤑','🤗','🤭','🫡','🤫','🤔','🫢','🤐','🥱','😤','😠','😡',
    '🤬','😈','👿','💀','☠️','💩','🤡','👹','👺','👻','👽','👾','🤖','😺','😸','😹','😻','😼','😽','🙀',
    '😿','😾','🙈','🙉','🙊','😱','😨','😰','😥','😢','😭','😓','😪','🥺','🫤','😔','😟','😞','😒','😕',
    '🫥','😣','😖','😩','😫','🤯','😤','😶','😑','😬','🙄','😯','😦','😧','😮','😲','🥸','🤥','🤫','😷',
    '🤒','🤕','🤢','🤮','🤧','🥵','🥶','🥴','😵','😵‍💫','🤠','🥳','🥸','😎','🤓','🧐',
  ],
  people: [
    '👋','🤚','🖐️','✋','🖖','🫱','🫲','🫳','🫴','👌','🤌','🤏','✌️','🤞','🫰','🤟','🤘','🤙','👈','👉',
    '👆','🖕','👇','☝️','🫵','👍','👎','✊','👊','🤛','🤜','👏','🙌','🫶','👐','🤲','🤝','🙏','✍️','💅',
    '🤳','💪','🦾','🦿','🦵','🦶','👂','🦻','👃','🫀','🫁','🧠','🦷','🦴','👀','👁️','👅','👄','🫦','💋',
    '👶','🧒','👦','👧','🧑','👱','👨','🧔','👩','🧓','👴','👵','🙍','🙎','🙅','🙆','💁','🙋','🧏','🙇',
    '🤦','🤷','👮','🕵️','💂','🥷','👷','🫅','🤴','👸','👰','🤵','🦸','🦹','🧙','🧝','🧛','🧟','🧞','🧜',
    '🧚','👼','🤰','🫄','🤱','🧑‍🍼','🎅','🤶','🧑‍🎄','🦊','🐱','🐶','🐺','🦝',
  ],
  animals: [
    '🐶','🐱','🐭','🐹','🐰','🦊','🐻','🐼','🐻‍❄️','🐨','🐯','🦁','🐮','🐷','🐽','🐸','🐵','🙈','🙉','🙊',
    '🐔','🐧','🐦','🐤','🦆','🦅','🦉','🦇','🐺','🐗','🐴','🦄','🐝','🪱','🐛','🦋','🐌','🐞','🐜','🪲',
    '🦟','🦗','🪳','🕷️','🦂','🐢','🐍','🦎','🦖','🦕','🐙','🦑','🦐','🦞','🦀','🐡','🐠','🐟','🐬','🐳',
    '🐋','🦈','🦭','🐊','🐅','🐆','��','🦍','🦧','🦣','🐘','🦛','🦏','🐪','🐫','🦒','🦘','🦬','🐃','🐂',
    '🐄','🫎','🫏','🐎','🐖','🐏','🐑','🦙','🐐','🦌','🐕','🐩','🦮','🐕‍🦺','🐈','🐈‍⬛','🪶','🐓','🦃',
    '🦤','🦚','🦜','🦢','🦩','🕊️','🐇','🦝','🦨','🦡','🦫','🦦','🦥','🐁','🐀','🐿️','🦔','🌵','🎄','🌲',
    '🌳','🌴','🪵','🌱','🌿','☘️','🍀','🎍','🎋','🍃','🍂','🍁','🍄','🐚','🪸','🌾','💐','🌷','🌹','🥀',
    '🌺','🌸','🌼','🌻','🌞','🌝','🌛','🌜','🌚','🌕','🌖','🌗','🌘','🌑','🌒','🌓','🌔','🌙','🌟','⭐',
    '🌠','🌌','☁️','⛅','🌤️','🌈','❄️','☃️','⛄','🌊','💧','🔥','🌪️','🌫️','🌬️',
  ],
  food: [
    '🍎','🍐','🍊','🍋','🍌','🍉','🍇','🍓','🫐','🍈','🍒','🍑','🥭','🍍','🥥','🥝','🍅','🍆','🥑','🫒',
    '🥦','🥬','🥒','🌶️','🫑','🥕','🧄','🧅','🥔','🍠','🫚','🥐','🥯','🍞','🥖','🥨','🧀','🥚','🍳','🧈',
    '🥞','🧇','🥓','🥩','🍗','🍖','🌭','🍔','🍟','🍕','🫓','🥪','🥙','🧆','🌮','🌯','🫔','🥗','🥘','🫕',
    '🥫','🍝','🍜','🍲','🍛','🍣','🍱','🥟','🦪','🍤','🍙','🍚','🍘','🍥','🥮','🍢','🧁','🍰','🎂','🍮',
    '🍭','🍬','🍫','🍿','🍩','🍪','🌰','🥜','🍯','🧃','🥤','🧋','☕','🍵','🫖','🍺','🍻','🥂','🍷','🫗',
    '🥃','🍸','🍹','🧉','🍾','🧊','🥄','🍴','🍽️','🥢','🫙','🧂',
  ],
  travel: [
    '🌍','🌎','🌏','🌐','🗺️','🧭','🏔️','⛰️','🌋','🗻','🏕️','🏖️','🏜️','🏝️','🏞️','🏟️','🏛️','🏗️','🧱','🏘️',
    '🏚️','🏠','🏡','🏢','🏣','🏤','🏥','🏦','🏨','🏩','🏪','🏫','🏬','🏭','🏯','🏰','💒','🗼','🗽','⛪',
    '🕌','🛕','🕍','⛩️','🕋','⛲','⛺','🏕️','🌁','🌃','🏙️','🌄','🌅','🌆','🌇','🌉','♨️','🎠','🎡','🎢',
    '💈','🎪','🚂','🚃','🚄','🚅','🚆','🚇','🚈','🚉','🚊','🚝','🚞','🚋','🚌','🚍','🚎','🚐','🚑','🚒',
    '🚓','🚔','🚕','🚖','🚗','🚘','🚙','🛻','🚚','🚛','🚜','🏎️','🏍️','🛵','🛺','🚲','🛴','🛹','🛼','🚏',
    '🛣️','🛤️','⛽','🚧','⚓','🛟','⛵','🚤','🛥️','🛳️','⛴️','🚢','✈️','🛩️','🛫','🛬','🪂','💺','🚁','🚟',
    '🚠','🚡','🛰️','🚀','🛸','🪐','🌠','🌌','🌙','⭐','🌟','💫','✨','⚡','🌈','☀️','🌤️','⛅','🌥️','☁️',
  ],
  activities: [
    '⚽','🏀','🏈','⚾','🥎','🎾','🏐','🏉','🥏','🎱','🏓','🏸','🏒','🥍','🏑','🏏','🪃','🥅','⛳','🪁',
    '🛝','🏹','🎣','🤿','🥊','🥋','🎽','🛹','🛼','🛷','⛸️','🥌','🎿','⛷️','🏂','🪂','🏋️','🤸','⛹️','🤺',
    '🤾','🏌️','🏇','🧘','🏄','🏊','🤽','🚣','🧗','🚵','🚴','🏆','🥇','🥈','🥉','🏅','🎖️','🏵️','🎗️','🎫',
    '🎟️','🎪','🤹','🎭','🩰','🎨','🎬','🎤','🎧','🎼','🎵','🎶','🥁','🪘','🎷','🎺','🎸','🪕','🎻','🪗',
    '🎹','🪈','🎲','♟️','🎯','🎳','🎮','🕹️','🎰','🧩','🧸','🪆','♠️','♥️','♦️','♣️','🃏','🀄','🎴',
  ],
  objects: [
    '⌚','📱','📲','💻','⌨️','🖥️','🖨️','🖱️','🖲️','💽','💾','💿','📀','📷','📸','📹','🎥','📽️','🎞️','📞',
    '☎️','📟','📠','📺','📻','🎙️','🎚️','🎛️','🧭','⏱️','⏲️','⏰','🕰️','⌛','⏳','📡','🔋','🪫','🔌','💡',
    '🔦','🕯️','🪔','🧯','🛢️','💸','💵','💴','💶','💷','🪙','💰','💳','💎','⚖️','🦯','🔧','🪛','🔨','⚒️',
    '🛠️','⛏️','🪚','🔩','🪤','🧱','⛓️','🧲','🔫','💣','🧨','🪓','🔪','🗡️','⚔️','🛡️','🪬','🔬','🔭','📡',
    '💉','🩸','💊','🩹','🩼','🩺','🩻','🚪','🛗','🪞','🪟','🛏️','🛋️','🪑','🚽','🪠','🚿','🛁','🪤','🧴',
    '🧷','🧹','🧺','🧻','🪣','🧼','🫧','🪥','🧽','🧯','🛒','🚬','⚰️','🪦','⚱️','🧿','🪬','🗺️','🧭','💈',
    '⚗️','🔭','🔬','🪬','🧲','🪝','🧲','💡','🔦','📦','📫','📪','📬','📭','📮','🗳️','✏️','✒️','🖋️','🖊️',
    '📝','📁','📂','🗂️','📅','📆','🗒️','🗓️','📇','📈','📉','📊','📋','📌','📍','🗺️','📎','🖇️','📏','📐',
    '✂️','🗃️','🗄️','🗑️','🔒','🔓','🔏','🔐','🔑','🗝️','🔨','🪓','⛏️','🔧','🪛','🔩','⚙️','🗜️','🔗','⛓️',
    '🧰','🪤','🪜','🧱','🔮','🧿','🪬','🧸','📿','💎','🔮','📚','📖','📰','🗞️','📓','📔','📒','📕','📗',
    '📘','📙','📜','📄','📃','📑','🗒️','📊','📈','📉',
  ],
  symbols: [
    '❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❤️‍🔥','❤️‍🩹','❣️','💕','💞','💓','💗','💖','💘','💝',
    '💟','☮️','✝️','☪️','🕉️','✡️','🔯','🪯','☯️','☦️','🛐','⛎','♈','♉','♊','♋','♌','♍','♎','♏','♐',
    '♑','♒','♓','🆔','⚛️','🉑','☢️','☣️','📴','📳','🈶','🈚','🈸','🈺','🈷️','✴️','🆚','💮','🉐','㊙️','㊗️',
    '🈴','🈵','🈹','🈲','🅰️','🅱️','🆎','🆑','🅾️','🆘','❌','⭕','🛑','⛔','📛','🚫','💯','💢','♨️','🔰',
    '✅','☑️','✔️','❎','🔱','⚜️','🔰','♻️','🈯','💹','❇️','✳️','❎','🌐','💠','Ⓜ️','🌀','💤','🏧','🚾',
    '♿','🅿️','🛗','🈳','🈹','🚰','🚹','🚺','🚻','🚼','🚽','⚠️','🔞','📵','🚯','🚱','🚳','📵','🔕','🔇',
    '🔈','🔉','🔊','📢','📣','🔔','🔕','🎵','🎶','⁉️','🔅','🔆','📶','🛜','📳','📴','♾️','✖️','➕','➖','➗',
    '🟰','♾️','‼️','⁉️','❓','❔','❗','❕','〰️','💱','💲','⚕️','♻️','⚜️','🔱','📛','🔰','⭕','✅','☑️','✔️',
    '🔲','🔳','▪️','▫️','◾','◽','◼️','◻️','⬛','⬜','🟥','🟧','🟨','🟩','🟦','🟪','🟫','🔶','🔷','🔸',
    '🔹','🔺','🔻','💠','🔘','🔲','🔳','🏁','🚩','🎌','🏴','🏳️',
  ],
  flags: [
    '🏁','🚩','🎌','🏴','🏳️','🏳️‍🌈','🏳️‍⚧️','🏴‍☠️','🇦🇨','🇦🇩','🇦🇪','🇦🇫','🇦🇬','🇦🇮','🇦🇱','🇦🇲','🇦🇴','🇦🇶',
    '🇦🇷','🇦🇸','🇦🇹','🇦🇺','🇦🇼','🇦🇽','🇦🇿','🇧🇦','🇧🇧','🇧🇩','🇧🇪','🇧🇫','🇧🇬','🇧🇭','🇧🇮','🇧🇯','🇧🇱','🇧🇲',
    '🇧🇳','🇧🇴','🇧🇶','🇧🇷','🇧🇸','🇧🇹','🇧🇻','🇧🇼','🇧🇾','🇧🇿','🇨🇦','🇨🇨','🇨🇩','🇨🇫','🇨🇬','🇨🇭','🇨🇮','🇨🇰',
    '🇨🇱','🇨🇲','🇨🇳','🇨🇴','🇨🇵','🇨🇷','🇨🇺','🇨🇻','🇨🇼','🇨🇽','🇨🇾','🇨🇿','🇩🇪','🇩🇬','🇩🇯','🇩🇰','🇩🇲','🇩🇴',
    '🇩🇿','🇪🇦','🇪🇨','🇪🇪','🇪🇬','🇪🇭','🇪🇷','🇪🇸','🇪🇹','🇪🇺','🇫🇮','🇫🇯','🇫🇰','🇫🇲','🇫🇴','🇫🇷','🇬🇦','🇬🇧',
    '🇬🇩','🇬🇪','🇬🇫','🇬🇬','🇬🇭','🇬🇮','🇬🇱','🇬🇲','🇬🇳','🇬🇵','🇬🇶','🇬🇷','🇬🇸','🇬🇹','🇬🇺','🇬🇼','🇬🇾','🇭🇰',
    '🇭🇲','🇭🇳','🇭🇷','🇭🇹','🇭🇺','🇮🇨','🇮🇩','🇮🇪','🇮🇱','🇮🇲','🇮🇳','🇮🇴','🇮🇶','🇮🇷','🇮🇸','🇮🇹','🇯🇪','🇯🇲',
    '🇯🇴','🇯🇵','🇰🇪','🇰🇬','🇰🇭','🇰🇮','🇰🇲','🇰🇳','🇰🇵','🇰🇷','🇰🇼','🇰🇾','🇰🇿','🇱🇦','🇱🇧','🇱🇨','🇱🇮','🇱🇰',
    '🇱🇷','🇱🇸','🇱🇹','🇱🇺','🇱🇻','🇱🇾','🇲🇦','🇲🇨','🇲🇩','🇲🇪','🇲🇫','🇲🇬','🇲🇭','🇲🇰','🇲🇱','🇲🇲','🇲🇳','🇲🇴',
    '🇲🇵','🇲🇶','🇲🇷','🇲🇸','🇲🇹','🇲🇺','🇲🇻','🇲🇼','🇲🇽','🇲🇾','🇲🇿','🇳🇦','🇳🇨','🇳🇪','🇳🇫','🇳🇬','🇳🇮','🇳🇱',
    '🇳🇴','🇳🇵','🇳🇷','🇳🇺','🇳🇿','🇴🇲','🇵🇦','🇵🇪','🇵🇫','🇵🇬','🇵🇭','🇵🇰','🇵🇱','🇵🇲','🇵🇳','🇵🇷','🇵🇸','🇵🇹',
    '🇵🇼','🇵🇾','🇶🇦','🇷🇪','🇷🇴','🇷🇸','🇷🇺','🇷🇼','🇸🇦','🇸🇧','🇸🇨','🇸🇩','🇸🇪','🇸🇬','🇸🇭','🇸🇮','🇸🇯','🇸🇰',
    '🇸🇱','🇸🇲','🇸🇳','🇸🇴','🇸🇷','🇸🇸','🇸🇹','🇸🇻','🇸🇽','🇸🇾','🇸🇿','🇹🇦','🇹🇨','🇹🇩','🇹🇫','🇹🇬','🇹🇭','🇹🇯',
    '🇹🇰','🇹🇱','🇹🇲','🇹🇳','🇹🇴','🇹🇷','🇹🇹','🇹🇻','🇹🇼','🇹🇿','🇺🇦','🇺🇬','🇺🇲','🇺🇳','🇺🇸','🇺🇾','🇺🇿','🇻🇦',
    '🇻🇨','🇻🇪','🇻🇬','🇻🇮','🇻🇳','🇻🇺','🇼🇫','🇼🇸','🇽🇰','🇾🇪','🇾🇹','🇿🇦','🇿🇲','🇿🇼',
  ],
}

const currentCategoryEmojis = computed(() => emojiData[activeEmojiCategory.value] || [])

let emojiPickerCloseHandler: ((e: MouseEvent) => void) | null = null

function removeEmojiPickerCloseHandler() {
  if (emojiPickerCloseHandler) {
    document.removeEventListener('click', emojiPickerCloseHandler, false)
    emojiPickerCloseHandler = null
  }
}

function toggleEmojiPicker(target: 'create' | 'edit') {
  if (emojiPickerVisible.value && emojiPickerTarget.value === target) {
    emojiPickerVisible.value = false
    removeEmojiPickerCloseHandler()
    return
  }
  emojiPickerTarget.value = target
  emojiPickerVisible.value = true

  nextTick(() => {
    const btnRef = target === 'create' ? createIconBtnRef.value : editIconBtnRef.value
    if (!btnRef) return
    const rect = btnRef.getBoundingClientRect()
    const pickerWidth = 320
    const pickerHeight = 280
    let left = rect.left + rect.width / 2 - pickerWidth / 2
    let top = rect.bottom + 8

    if (left < 8) left = 8
    if (left + pickerWidth > window.innerWidth - 8) left = window.innerWidth - pickerWidth - 8
    if (top + pickerHeight > window.innerHeight - 8) top = rect.top - pickerHeight - 8

    emojiPickerStyle.value = {
      position: 'fixed',
      left: `${left}px`,
      top: `${top}px`,
      width: `${pickerWidth}px`,
      zIndex: '9999',
    }

    // 注册 document click 以点击外部关闭（setTimeout 跳过当前触发的 click 事件）
    removeEmojiPickerCloseHandler()
    emojiPickerCloseHandler = () => {
      emojiPickerVisible.value = false
      removeEmojiPickerCloseHandler()
    }
    setTimeout(() => {
      document.addEventListener('click', emojiPickerCloseHandler!, false)
    }, 0)
  })
}

function selectEmoji(emoji: string) {
  if (emojiPickerTarget.value === 'create') {
    newTag.value.icon = newTag.value.icon === emoji ? '' : emoji
  } else {
    editingTag.value.icon = editingTag.value.icon === emoji ? '' : emoji
  }
  emojiPickerVisible.value = false
  removeEmojiPickerCloseHandler()
}

const contextMenuVisible = ref(false)
const contextMenuTrigger = ref<HTMLElement>()
const selectedTag = ref<Tag | null>(null)
const draggingTagId = ref<number | null>(null)
const tagListRef = ref<HTMLElement | null>(null)

const contextMenuAnchor = (() => {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;pointer-events:none'
  document.body.appendChild(el)
  return el
})()
const reorderTargetTagId = ref<number | null>(null)
const listDropActive = ref(false)

// 加载标签，根据当前工作目录过滤
function loadTagsForWorkspace() {
  const workspace = appStore.currentWorkspace
  tagStore.loadTags(workspace || undefined)
}

onMounted(() => {
  loadTagsForWorkspace()
  window.addEventListener('close-context-menus', closeContextMenu)
})

onUnmounted(() => {
  window.removeEventListener('close-context-menus', closeContextMenu)
  removeEmojiPickerCloseHandler()
})

// 监听工作目录变化，重新加载标签
watch(() => appStore.currentWorkspace, (newWorkspace, oldWorkspace) => {
  if (newWorkspace !== oldWorkspace) {
    console.log('[TagPanel] Workspace changed from', oldWorkspace, 'to', newWorkspace)
    // 清除标签选择
    tagStore.clearSelection()
    // 重新加载标签
    loadTagsForWorkspace()
    // 如果当前有标签过滤，清除过滤并重新搜索
    if (tagStore.hasSelection) {
      fileStore.search({ root: newWorkspace || undefined })
    }
  }
})

function handleTagClick(tagId: number, event: MouseEvent) {
  const multi = event.ctrlKey || event.metaKey

  // 检查是否点击的是已选中的标签
  if (tagStore.selectedTagIds.has(tagId) && !multi) {
    // 如果是已选中的标签且没有按多选键，则取消选择
    tagStore.clearSelection()
    // 重新搜索当前工作区的文件
    if (appStore.currentWorkspace) {
      fileStore.search({ root: appStore.currentWorkspace })
    } else {
      fileStore.search({})
    }
    return
  }

  tagStore.selectTag(tagId, multi)

  // 更新文件搜索
  if (tagStore.selectedTagIds.size > 0) {
    fileStore.search({
      root: appStore.currentWorkspace || undefined,
      tags: Array.from(tagStore.selectedTagIds),
      match_all_tags: false,
    })
  } else {
    // 如果没有选中任何标签，搜索当前工作区
    if (appStore.currentWorkspace) {
      fileStore.search({ root: appStore.currentWorkspace })
    } else {
      fileStore.search({})
    }
  }
}

function clearFilter() {
  tagStore.clearSelection()
  // 重新搜索当前工作区的文件
  if (appStore.currentWorkspace) {
    fileStore.search({ root: appStore.currentWorkspace })
  } else {
    fileStore.search({})
  }
}

async function createTag() {
  if (!newTag.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }

  try {
    // 传入当前工作目录，实现标签隔离
    const workspace = appStore.currentWorkspace || undefined
    await tagStore.createTag(
      newTag.value.name,
      newTag.value.color,
      newTag.value.description,
      workspace,
      newTag.value.icon || undefined,
    )
    ElMessage.success('标签创建成功')
    showCreateDialog.value = false
    newTag.value = { name: '', color: '#409EFF', icon: '', description: '' }
  } catch (error: any) {
    // 处理 409 冲突错误
    if (error?.response?.status === 409) {
      ElMessage.error('该工作目录下已存在同名标签')
    } else {
      ElMessage.error('标签创建失败')
    }
  }
}

function resetDragState() {
  draggingTagId.value = null
  reorderTargetTagId.value = null
  listDropActive.value = false
  clearTagDragState()
}

// 面板根元素 dragover：标签拖拽时防止在非 tag-list 区域显示禁止图标
function handlePanelDragOver(event: DragEvent) {
  if (isTagDragInProgress()) {
    event.preventDefault()
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move'
    }
  }
}

function handleTagDragStart(tagId: number, event: DragEvent) {
  draggingTagId.value = tagId
  setTagDragData(event, tagId)
}

function handleTagDragOver(tagId: number, event: DragEvent) {
  if (!isTagDragInProgress() && !hasTagDrag(event)) {
    return
  }

  reorderTargetTagId.value = draggingTagId.value === tagId ? null : tagId
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

function handleTagDragLeave(tagId: number) {
  if (reorderTargetTagId.value === tagId) {
    reorderTargetTagId.value = null
  }
}

function handleTagListDragOver(event: DragEvent) {
  if (isTagDragInProgress() || hasTagDrag(event)) {
    listDropActive.value = true
  }
}

function handleTagListDragLeave() {
  listDropActive.value = false
}

async function handleTagDrop(tag: Tag, event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)

  if (draggedTagId !== null && draggedTagId !== tag.id) {
    // 根据鼠标在目标 tag 的上/下半决定插入位置
    const el = (event.currentTarget as HTMLElement)
    const rect = el.getBoundingClientRect()
    const isLowerHalf = event.clientY > rect.top + rect.height / 2
    const targetId = isLowerHalf ? getNextTagId(tag.id) : tag.id
    tagStore.reorderTags(draggedTagId, targetId)
  }
  resetDragState()
}

async function handleTagListDrop(event: DragEvent) {
  const draggedTagId = getDraggedTagId(event)

  if (draggedTagId !== null) {
    const targetTagId = getTagIdNearY(event.clientY, draggedTagId)
    tagStore.reorderTags(draggedTagId, targetTagId)
  }

  resetDragState()
}

// 根据鼠标 Y 坐标找到最近的目标标签 id
// 返回 null 表示追加到末尾
function getTagIdNearY(clientY: number, excludeTagId: number): number | null {
  if (!tagListRef.value) return null

  const items = Array.from(tagListRef.value.querySelectorAll<HTMLElement>('.tag-item'))
  if (!items.length) return null

  let nearestId: number | null = null
  let nearestDist = Infinity

  for (const item of items) {
    const rect = item.getBoundingClientRect()
    const itemCenter = rect.top + rect.height / 2
    const dist = Math.abs(clientY - itemCenter)

    if (dist < nearestDist) {
      nearestDist = dist
      // 读取 tag id（通过 data 属性或 key）
      const idStr = item.dataset.tagId
      if (idStr) {
        const id = Number(idStr)
        if (id !== excludeTagId) {
          // 鼠标在该 tag 下半部时，插到它后面（targetId = 下一个 tag），否则插到它前面
          nearestId = clientY > itemCenter ? getNextTagId(id) : id
        }
      }
    }
  }

  return nearestId
}

function getNextTagId(tagId: number): number | null {
  const order = tagStore.orderedTags
  const idx = order.findIndex(t => t.id === tagId)
  return idx !== -1 && idx + 1 < order.length ? order[idx + 1].id : null
}

function closeContextMenu() {
  contextMenuVisible.value = false
}

function handleContextMenu(tag: Tag, event: MouseEvent) {
  selectedTag.value = tag

  // 关闭其他面板的右键菜单
  window.dispatchEvent(new Event('close-context-menus'))

  contextMenuAnchor.style.left = `${event.clientX}px`
  contextMenuAnchor.style.top = `${event.clientY}px`
  contextMenuTrigger.value = contextMenuAnchor
  contextMenuVisible.value = true
}

function onContextMenuVisibleChange(val: boolean) {
  contextMenuVisible.value = val
}

function editTag() {
  if (!selectedTag.value) return

  editingTag.value = { ...selectedTag.value, icon: selectedTag.value.icon || '' }
  contextMenuVisible.value = false
  showEditDialog.value = true
}

async function saveTagEdit() {
  if (!editingTag.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }

  try {
    await tagStore.updateTag(editingTag.value.id, {
      name: editingTag.value.name,
      color: editingTag.value.color,
      icon: editingTag.value.icon || undefined,
      description: editingTag.value.description,
    })
    ElMessage.success('标签更新成功')
    showEditDialog.value = false
  } catch (error) {
    ElMessage.error('标签更新失败')
  }
}

async function confirmDeleteTag() {
  if (!selectedTag.value) return

  const tag = selectedTag.value
  contextMenuVisible.value = false

  try {
    await ElMessageBox.confirm(
      `确定要删除标签 "${tag.name}" 吗？${tag.file_count > 0 ? `该标签已关联 ${tag.file_count} 个文件。` : ''}`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    await tagStore.deleteTag(tag.id)

    // 如果该标签正在被过滤，清除过滤
    if (tagStore.selectedTagIds.has(tag.id)) {
      tagStore.clearSelection()
      if (appStore.currentWorkspace) {
        fileStore.search({ root: appStore.currentWorkspace })
      } else {
        fileStore.search({})
      }
    }

    ElMessage.success('标签删除成功')
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('标签删除失败')
    }
  }
}
</script>

<style scoped>
.tag-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.filter-status {
  padding: 8px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.filter-status :deep(.el-alert) {
  padding: 8px 12px;
}

.filter-status .filter-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.tag-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.tag-list.list-drop-active {
  background: color-mix(in srgb, var(--color-accent-light) 45%, transparent);
}

.tag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  margin-bottom: 4px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-item:hover {
  opacity: 0.8;
}

.tag-item.selected {
  border-width: 2px;
}

.tag-item.drag-source {
  opacity: 0.65;
}

.tag-item.drag-over {
  border-color: var(--color-accent) !important;
  transform: translateX(4px);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-accent) 50%, transparent);
}

.tag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-icon {
  font-size: 15px;
  line-height: 1;
  flex-shrink: 0;
  width: 18px;
  text-align: center;
}

.tag-name {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary);
}

.tag-count {
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: 10px;
}

/* 对话框图标区域 */
.dialog-icon-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 0 8px;
}

.dialog-icon-btn {
  width: 72px;
  height: 72px;
  border-radius: 16px;
  border: 2px dashed var(--color-border);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--color-bg-secondary);
  user-select: none;
}

.dialog-icon-btn:hover {
  border-style: solid;
  background: var(--color-bg-tertiary);
}

.dialog-icon-emoji {
  font-size: 36px;
  line-height: 1;
}

.dialog-icon-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
}

.dialog-icon-hint {
  font-size: 10px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.dialog-icon-clear {
  font-size: 12px;
  color: var(--color-text-tertiary);
  cursor: pointer;
  text-decoration: underline;
  user-select: none;
}

.dialog-icon-clear:hover {
  color: var(--color-danger);
}

/* Emoji 选择器弹出层 */
.context-menu {
  padding: 4px 0;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.context-menu-item:hover {
  background-color: var(--color-bg-secondary);
}

.context-menu-item.delete {
  color: var(--color-danger);
}

.context-menu-item.delete:hover {
  background-color: var(--color-danger-light);
}
</style>

<style>
/* Emoji picker — teleported to <body>, must not be scoped */
.emoji-picker-popup {
  background: var(--color-bg-primary, #fff);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.emoji-picker-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 8px 0;
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
}

.emoji-picker-tab {
  font-size: 18px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  user-select: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.emoji-picker-tab:hover {
  background: var(--color-bg-secondary);
}

.emoji-picker-tab.active {
  border-bottom-color: var(--color-accent);
  background: var(--color-accent-light);
}

.emoji-picker-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 2px;
  padding: 8px;
  overflow-y: auto;
  max-height: 220px;
}

.emoji-picker-item {
  font-size: 20px;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s;
  user-select: none;
  border: 1px solid transparent;
}

.emoji-picker-item:hover {
  background: var(--color-bg-secondary);
}

.emoji-picker-item.active {
  background: var(--color-accent-light);
  border-color: var(--color-accent);
}
</style>
