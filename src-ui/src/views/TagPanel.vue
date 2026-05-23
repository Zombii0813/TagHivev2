<template>
  <div class="tag-panel" @dragover="handlePanelDragOver">
    <div class="panel-header">
      <h3>标签</h3>
      <div class="header-actions">
        <el-button
          :type="isManageMode ? 'warning' : 'default'"
          size="small"
          @click="toggleManageMode"
        >
          {{ isManageMode ? '完成' : '管理' }}
        </el-button>
        <el-button
          v-if="!isManageMode"
          type="primary"
          size="small"
          :icon="Plus"
          @click="openCreateDialog"
        >
          新建
        </el-button>
      </div>
    </div>

    <!-- 标签层级过滤模式切换：含子标签 vs 仅本标签 -->
    <div v-if="!isManageMode" class="tag-filter-mode">
      <el-radio-group
        :model-value="tagStore.tagFilterMode"
        size="small"
        @change="handleFilterModeChange"
      >
        <el-radio-button value="with-descendants" title="父标签匹配自身及所有子标签的文件">含子标签</el-radio-button>
        <el-radio-button value="self-only" title="父标签仅匹配直接打在自身的文件">仅本标签</el-radio-button>
      </el-radio-group>
      <el-button
        v-if="tagStore.hasSelection"
        type="primary"
        link
        size="small"
        :icon="Close"
        class="filter-clear-btn"
        @click="clearFilter"
      >
        清除过滤
      </el-button>
    </div>

    <!-- 管理模式提示 -->
    <div v-if="isManageMode" class="manage-hint">
      <span>拖动标签可调整顺序</span>
    </div>

    <div
      ref="tagListRef"
      class="tag-list"
      :class="{ 'manage-mode': isManageMode }"
      v-loading="tagStore.isLoading"
    >
      <template v-for="(node, index) in tagStore.flatTagList" :key="node.tag.id">
        <div
          class="tag-item"
          :class="{
            selected: !isManageMode && tagStore.isTagActive(node.tag.id),
            'selected-direct': !isManageMode && tagStore.selectedTagIds.has(node.tag.id),
            'manage-dragging': isManageMode && manageDragState.sourceId === node.tag.id,
            'manage-item': isManageMode,
          }"
          :style="{ ...getTagItemStyle(node.tag, index), paddingLeft: `${10 + node.depth * 16}px` }"
          :data-tag-id="node.tag.id"
          :draggable="!isManageMode"
          @click="!isManageMode && handleTagClick(node.tag.id, $event)"
          @contextmenu.prevent="!isManageMode && handleContextMenu(node.tag, $event)"
          @dragstart="!isManageMode && handleTagDragStart(node.tag.id, $event)"
          @dragend="!isManageMode && clearTagDragState()"
          @pointerdown="isManageMode && handleManagePointerDown(node.tag.id, $event)"
        >
          <span v-if="isManageMode" class="manage-drag-handle">⠿</span>
          <!-- 展开/折叠按钮（有子标签时显示） -->
          <span
            v-if="node.children.length > 0 && !isManageMode"
            class="tag-expand-btn"
            @click.stop="tagStore.toggleExpand(node.tag.id)"
          >
            <el-icon :size="10">
              <ArrowDown v-if="tagStore.expandedTagIds.has(node.tag.id)" />
              <ArrowRight v-else />
            </el-icon>
          </span>
          <span v-else-if="!isManageMode && node.depth > 0" class="tag-child-indent"></span>
          <span v-if="node.tag.icon" class="tag-icon">{{ node.tag.icon }}</span>
          <span v-else class="tag-dot" :style="{ backgroundColor: node.tag.color }"></span>
          <span class="tag-name">{{ node.tag.name }}</span>
          <span class="tag-count">{{ node.tag.file_count }}</span>
        </div>
      </template>
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

      <el-form :model="newTag" label-position="top">
        <el-form-item label="颜色">
          <div class="color-picker-panel">
            <div class="color-preset-grid">
              <div
                v-for="c in PRESET_COLORS"
                :key="c"
                class="color-preset-swatch"
                :class="{ active: newTag.color === c }"
                :style="{ backgroundColor: c }"
                :title="c"
                @click="newTag.color = c"
              />
            </div>
            <div class="color-custom-row">
              <div class="color-custom-preview" :style="{ backgroundColor: newTag.color }" />
              <el-input
                v-model="newTag.color"
                placeholder="#409EFF"
                size="small"
                class="color-custom-input"
                @blur="validateColor(newTag, 'color')"
              />
            </div>
          </div>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="newTag.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="newTag.description"
            type="textarea"
            placeholder="可选描述"
          />
        </el-form-item>
        <el-form-item label="父标签">
          <el-select v-model="newTag.parentId" placeholder="无（顶级标签）" clearable style="width:100%">
            <el-option :value="null" label="无（顶级标签）" />
            <el-option
              v-for="t in tagStore.tags.filter(t => t.id !== 0)"
              :key="t.id"
              :value="t.id"
              :label="t.name"
            />
          </el-select>
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
        <div class="context-menu-item" @click="createChildTag">
          <el-icon><Plus /></el-icon>
          <span>创建子标签</span>
        </div>
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

      <el-form :model="editingTag" label-position="top">
        <el-form-item label="颜色">
          <div class="color-picker-panel">
            <div class="color-preset-grid">
              <div
                v-for="c in PRESET_COLORS"
                :key="c"
                class="color-preset-swatch"
                :class="{ active: editingTag.color === c }"
                :style="{ backgroundColor: c }"
                :title="c"
                @click="editingTag.color = c"
              />
            </div>
            <div class="color-custom-row">
              <div class="color-custom-preview" :style="{ backgroundColor: editingTag.color }" />
              <el-input
                v-model="editingTag.color"
                placeholder="#409EFF"
                size="small"
                class="color-custom-input"
                @blur="validateColor(editingTag, 'color')"
              />
            </div>
          </div>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="editingTag.name" placeholder="输入标签名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="editingTag.description"
            type="textarea"
            placeholder="可选描述"
          />
        </el-form-item>
        <el-form-item label="父标签">
          <el-select v-model="editingTag.parent_id" placeholder="无（顶级标签）" clearable style="width:100%">
            <el-option :value="null" label="无（顶级标签）" />
            <el-option
              v-for="t in tagStore.tags.filter(t => t.id !== editingTag.id)"
              :key="t.id"
              :value="t.id"
              :label="t.name"
            />
          </el-select>
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
import { Plus, Close, Edit, Delete, ArrowRight, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTagStore } from '../stores/tags'
import { useFileStore } from '../stores/files'
import { useAppStore } from '../stores/app'
import type { Tag } from '../types'
import { setTagDragData, clearTagDragState, isTagDragInProgress } from '../utils/drag'
import { pickDistinctColor, PRESET_COLORS } from '../utils/color'

const tagStore = useTagStore()
const fileStore = useFileStore()
const appStore = useAppStore()

function validateColor(obj: Record<string, any>, key: string) {
  const val: string = (obj[key] || '').trim()
  if (!val) { obj[key] = '#409EFF'; return }
  // 补全 # 前缀
  const normalized = val.startsWith('#') ? val : '#' + val
  if (/^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/.test(normalized)) {
    obj[key] = normalized.toUpperCase()
  } else {
    obj[key] = '#409EFF'
  }
}

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const newTag = ref({
  name: '',
  color: '#409EFF',
  icon: '',
  description: '',
  parentId: null as number | null,
})

// 打开新建对话框前，挑一个与现有标签不撞色的默认颜色，提升区分度
function openCreateDialog() {
  const used = tagStore.tags.map(t => t.color).filter((c): c is string => !!c)
  newTag.value = {
    name: '',
    color: pickDistinctColor(used, PRESET_COLORS),
    icon: '',
    description: '',
    parentId: null,
  }
  showCreateDialog.value = true
}

const editingTag = ref<Tag & { description?: string }>({
  id: 0,
  name: '',
  color: '#409EFF',
  icon: '',
  description: '',
  parent_id: null,
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
const tagListRef = ref<HTMLElement | null>(null)

// 管理模式
const isManageMode = ref(false)

// 管理模式下的拖拽状态（pointer events 驱动）
interface ManageDragState {
  sourceId: number | null
  insertIndex: number | null        // 当前插入点索引（在 orderedTags 中）
  itemMidYs: number[]               // 拖拽开始时各 item 中点 Y 的快照
  itemHeight: number                // item 高度快照
  ghostEl: HTMLElement | null       // 跟随鼠标的 clone 元素
  startY: number                    // 指针起始 Y
  sourceIndex: number               // 被拖项的原始索引
}
const manageDragState = ref<ManageDragState>({
  sourceId: null,
  insertIndex: null,
  itemMidYs: [],
  itemHeight: 36,
  ghostEl: null,
  startY: 0,
  sourceIndex: -1,
})

function toggleManageMode() {
  if (isManageMode.value) {
    isManageMode.value = false
    endManageDrag(false)
  } else {
    // 退出过滤状态再进入管理模式
    tagStore.clearSelection()
    isManageMode.value = true
  }
}

// 计算 tag-item 的内联样式（管理模式下加入 transform）
function getTagItemStyle(tag: Tag, index: number): Record<string, string> {
  const color = tag.color ?? '#409EFF'
  const base: Record<string, string> = {
    backgroundColor: color + '20',
    borderColor: color,
    // 用 CSS 变量把标签色透传给 .selected 状态使用（inset box-shadow 模拟加粗边框）
    '--tag-color': color,
  }
  if (!isManageMode.value) return base

  const ds = manageDragState.value
  if (ds.sourceId === null || ds.insertIndex === null) return base

  const si = ds.sourceIndex
  const ii = ds.insertIndex
  const itemH = ds.itemHeight

  if (index === si) {
    // 被拖项本身：透明占位
    return { ...base, opacity: '0', pointerEvents: 'none' }
  }

  // 其他项根据插入点计算偏移
  let shift = 0
  if (si < ii) {
    // 向下拖：si+1 ~ ii-1 的项向上移
    if (index > si && index < ii) shift = -(itemH + 4)
  } else {
    // 向上拖：ii ~ si-1 的项向下移
    if (index >= ii && index < si) shift = itemH + 4
  }

  if (shift !== 0) {
    return { ...base, transform: `translateY(${shift}px)`, transition: 'transform 0.18s cubic-bezier(0.25,0.46,0.45,0.94)' }
  }
  return { ...base, transition: 'transform 0.18s cubic-bezier(0.25,0.46,0.45,0.94)' }
}

function handleManagePointerDown(tagId: number, event: PointerEvent) {
  if (!isManageMode.value) return
  event.preventDefault()

  const tags = tagStore.flatTagList
  const sourceIndex = tags.findIndex(n => n.tag.id === tagId)
  if (sourceIndex === -1) return

  // 快照所有 item 的中点 Y（此时 DOM 尚未变化）
  const items = Array.from(tagListRef.value?.querySelectorAll<HTMLElement>('.tag-item') ?? [])
  const itemHeight = items.length > 0 ? items[0].getBoundingClientRect().height : 36
  const midYs = items.map(el => {
    const r = el.getBoundingClientRect()
    return r.top + r.height / 2
  })

  // 创建 ghost clone
  const srcEl = items[sourceIndex]
  const ghost = srcEl.cloneNode(true) as HTMLElement
  const srcRect = srcEl.getBoundingClientRect()
  ghost.style.cssText = `
    position: fixed;
    left: ${srcRect.left}px;
    top: ${srcRect.top}px;
    width: ${srcRect.width}px;
    height: ${srcRect.height}px;
    pointer-events: none;
    z-index: 9999;
    opacity: 0.92;
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.22);
    transition: none;
    transform: scale(1.03);
  `
  document.body.appendChild(ghost)

  manageDragState.value = {
    sourceId: tagId,
    insertIndex: sourceIndex,
    itemMidYs: midYs,
    itemHeight,
    ghostEl: ghost,
    startY: event.clientY,
    sourceIndex,
  }

  // 捕获指针
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  target.addEventListener('pointermove', handleManagePointerMove)
  target.addEventListener('pointerup', handleManagePointerUp)
  target.addEventListener('pointercancel', handleManagePointerCancel)
}

function handleManagePointerMove(event: PointerEvent) {
  const ds = manageDragState.value
  if (ds.sourceId === null || !ds.ghostEl) return
  event.preventDefault()

  const deltaY = event.clientY - ds.startY

  // 移动 ghost：以初始 item 顶部位置 + 偏移
  const origTop = ds.itemMidYs[ds.sourceIndex] - ds.itemHeight / 2
  ds.ghostEl.style.top = `${origTop + deltaY}px`

  // 用初始 midY 快照计算插入点，跳过 source 自身行
  const midYs = ds.itemMidYs
  const cursorY = event.clientY
  let insertIdx = midYs.length // 默认末尾
  for (let i = 0; i < midYs.length; i++) {
    if (i === ds.sourceIndex) continue
    if (cursorY < midYs[i]) {
      insertIdx = i
      break
    }
  }
  ds.insertIndex = insertIdx
}

function handleManagePointerUp(event: PointerEvent) {
  endManageDrag(true)
  cleanupManagePointerListeners(event.currentTarget as HTMLElement, event.pointerId)
}

function handleManagePointerCancel(event: PointerEvent) {
  endManageDrag(false)
  cleanupManagePointerListeners(event.currentTarget as HTMLElement, event.pointerId)
}

function cleanupManagePointerListeners(target: HTMLElement, pointerId: number) {
  target.releasePointerCapture(pointerId)
  target.removeEventListener('pointermove', handleManagePointerMove)
  target.removeEventListener('pointerup', handleManagePointerUp)
  target.removeEventListener('pointercancel', handleManagePointerCancel)
}

function endManageDrag(commit: boolean) {
  const ds = manageDragState.value
  if (ds.ghostEl) {
    ds.ghostEl.remove()
  }
  if (commit && ds.sourceId !== null && ds.insertIndex !== null) {
    const nodes = tagStore.flatTagList
    // 将 insertIndex 转换为目标 tag id
    let targetId: number | null = null
    const ii = ds.insertIndex
    const si = ds.sourceIndex
    // 有效移动判断
    if (ii !== si && ii !== si + 1) {
      // insertIndex 是在原始数组中的位置
      // 注意：insertIndex 可能等于 sourceIndex（不动）或 sourceIndex+1（相当于不动）
      if (ii < nodes.length) {
        targetId = nodes[ii].tag.id
      } else {
        targetId = null // 移到末尾
      }
      tagStore.reorderTags(ds.sourceId, targetId)
    }
  }
  manageDragState.value = {
    sourceId: null,
    insertIndex: null,
    itemMidYs: [],
    itemHeight: 36,
    ghostEl: null,
    startY: 0,
    sourceIndex: -1,
  }
}

const contextMenuAnchor = (() => {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;pointer-events:none'
  document.body.appendChild(el)
  return el
})()

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
  endManageDrag(false)
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

function restoreCurrentView() {
  // folder 模式且在子目录中：回到该子目录的文件列表
  if (fileStore.browseMode === 'folder' && fileStore.currentFolderPath) {
    fileStore.loadFolderContents(fileStore.currentFolderPath)
  } else if (appStore.currentWorkspace) {
    fileStore.search({ root: appStore.currentWorkspace })
  } else {
    fileStore.search({})
  }
}

function getSearchRoot(): string | undefined {
  // folder 模式且在子目录中：搜索范围限定在当前子目录
  if (fileStore.browseMode === 'folder' && fileStore.currentFolderPath) {
    return fileStore.currentFolderPath
  }
  return appStore.currentWorkspace || undefined
}

function handleTagClick(tagId: number, event: MouseEvent) {
  const multi = event.ctrlKey || event.metaKey

  // 检查是否点击的是已选中的标签
  if (tagStore.selectedTagIds.has(tagId) && !multi) {
    // 如果是已选中的标签且没有按多选键，则取消选择，回到当前目录视图
    tagStore.clearSelection()
    restoreCurrentView()
    return
  }

  tagStore.selectTag(tagId, multi)

  // 更新文件搜索（实际下发后代展开后的标签集合，由 store 根据当前模式计算）
  if (tagStore.selectedTagIds.size > 0) {
    fileStore.search({
      root: getSearchRoot(),
      tags: Array.from(tagStore.effectiveTagIds),
      match_all_tags: false,
    })
  } else {
    restoreCurrentView()
  }
}

function handleFilterModeChange(value: string | number | boolean | undefined) {
  if (value !== 'with-descendants' && value !== 'self-only') return
  tagStore.setTagFilterMode(value)
  // 已有选中标签时，按新模式重新触发查询
  if (tagStore.selectedTagIds.size > 0) {
    fileStore.search({
      root: getSearchRoot(),
      tags: Array.from(tagStore.effectiveTagIds),
      match_all_tags: false,
    })
  }
}

function clearFilter() {
  tagStore.clearSelection()
  restoreCurrentView()
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
      newTag.value.parentId,
    )
    ElMessage.success('标签创建成功')
    showCreateDialog.value = false
    newTag.value = { name: '', color: '#409EFF', icon: '', description: '', parentId: null }
  } catch (error: any) {
    // 处理 409 冲突错误
    if (error?.response?.status === 409) {
      ElMessage.error('该工作目录下已存在同名标签')
    } else {
      ElMessage.error('标签创建失败')
    }
  }
}

// 面板根元素 dragover：标签拖拽时防止在非 tag-list 区域显示禁止图标
function handlePanelDragOver(event: DragEvent) {
  if (isTagDragInProgress()) {
    event.preventDefault()
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy'
    }
  }
}

function handleTagDragStart(tagId: number, event: DragEvent) {
  const tag = tagStore.getTagById(tagId)
  setTagDragData(event, tagId, tag ? { name: tag.name, color: tag.color, icon: tag.icon } : undefined)
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

// 右键"创建子标签"：以当前标签为父，复用新建对话框
function createChildTag() {
  if (!selectedTag.value) return
  const parent = selectedTag.value
  contextMenuVisible.value = false

  const used = tagStore.tags.map(t => t.color).filter((c): c is string => !!c)
  newTag.value = {
    name: '',
    color: pickDistinctColor(used, PRESET_COLORS),
    icon: '',
    description: '',
    parentId: parent.id,
  }
  // 展开父节点，便于创建后立即可见
  if (!tagStore.expandedTagIds.has(parent.id)) {
    tagStore.toggleExpand(parent.id)
  }
  showCreateDialog.value = true
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
      parent_id: editingTag.value.parent_id === undefined ? null : editingTag.value.parent_id,
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

  // 收集后代信息：子标签存在时，需要询问是同删还是升级保留
  const directChildren = tagStore.tags.filter(t => t.parent_id === tag.id)
  const descendantIds = tagStore.getDescendantIds(tag.id)
  const hasChildren = directChildren.length > 0

  // action 决定删除策略：
  //   'all'          —— 连同所有后代一起删除
  //   'children-up'  —— 仅删父标签，直接子标签的 parent_id 改为父标签自身的 parent_id（即整体上升一层）
  let action: 'all' | 'children-up' | null = null

  try {
    if (hasChildren) {
      try {
        await ElMessageBox.confirm(
          `标签「${tag.name}」下包含 ${descendantIds.length} 个子标签，是否一并删除？\n选择"保留子标签"会将其层级提升一层。`,
          '删除标签',
          {
            confirmButtonText: '全部删除',
            cancelButtonText: '保留子标签',
            type: 'warning',
            distinguishCancelAndClose: true,
            dangerouslyUseHTMLString: false,
          }
        )
        action = 'all'
      } catch (rejection) {
        // 'cancel' = 点击"保留子标签"按钮；'close' = 点 X 或按 Esc 整体取消
        if (rejection === 'cancel') {
          action = 'children-up'
        } else {
          return
        }
      }
    } else {
      await ElMessageBox.confirm(
        `确定要删除标签 "${tag.name}" 吗？${tag.file_count > 0 ? `该标签已关联 ${tag.file_count} 个文件。` : ''}`,
        '删除确认',
        {
          confirmButtonText: '删除',
          cancelButtonText: '取消',
          type: 'warning',
        }
      )
      action = 'all'
    }
  } catch {
    return
  }

  try {
    if (action === 'children-up') {
      // 直接子标签的 parent_id 升级为被删标签的 parent_id（顶级则为 null）；
      // 孙子标签的 parent 仍指向其直接父，无需调整。
      const newParentId: number | null = tag.parent_id ?? null
      for (const child of directChildren) {
        await tagStore.updateTag(child.id, { parent_id: newParentId })
      }
      await tagStore.deleteTag(tag.id)
    } else {
      // 全部删除：先删后代（任意顺序均可，后代先于祖先即可避免 SET NULL 漂移）
      for (const id of descendantIds) {
        await tagStore.deleteTag(id)
      }
      await tagStore.deleteTag(tag.id)
    }

    // 如果该标签或其后代正在被过滤，清除过滤
    if (tagStore.selectedTagIds.has(tag.id) || descendantIds.some(id => tagStore.selectedTagIds.has(id))) {
      tagStore.clearSelection()
      restoreCurrentView()
    }

    ElMessage.success('标签删除成功')
  } catch (error) {
    console.error('Failed to delete tag:', error)
    ElMessage.error('标签删除失败')
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

.header-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.manage-hint {
  padding: 6px 16px;
  background: color-mix(in srgb, var(--color-warning, #e6a23c) 12%, transparent);
  border-bottom: 1px solid color-mix(in srgb, var(--color-warning, #e6a23c) 30%, transparent);
  font-size: 12px;
  color: var(--color-warning, #e6a23c);
  text-align: center;
}

.filter-status {
  display: none;
}

.tag-filter-mode {
  padding: 6px 16px 8px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.tag-filter-mode :deep(.el-radio-button__inner) {
  padding: 4px 12px;
  font-size: 12px;
}

.filter-clear-btn {
  margin-left: auto;
}

.tag-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  transition: background-color 0.2s ease, border-color 0.2s ease;
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

.tag-item.manage-item {
  cursor: grab;
  user-select: none;
}

.tag-item.manage-item:active,
.tag-item.manage-dragging {
  cursor: grabbing;
}

.tag-item:hover {
  opacity: 0.8;
}

.tag-item.selected {
  /* 用 inset box-shadow 在已有 1px 边框内侧再叠 1px，等效"边框加粗到 2px"，
     但不改变盒模型尺寸，避免触发选中态的位置偏移。
     --tag-color 由内联样式 getTagItemStyle 注入，与 border-color 同色。 */
  box-shadow: inset 0 0 0 1px var(--tag-color, currentColor);
}

.manage-drag-handle {
  font-size: 14px;
  color: var(--color-text-tertiary);
  cursor: grab;
  flex-shrink: 0;
  line-height: 1;
  letter-spacing: -1px;
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

.tag-expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  cursor: pointer;
  border-radius: 3px;
  transition: background-color 0.15s;
}

.tag-expand-btn:hover {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.tag-child-indent {
  width: 14px;
  flex-shrink: 0;
}

/* 子标签左侧竖线 */
.tag-item[style*="padding-left: 26px"],
.tag-item[style*="padding-left: 42px"] {
  position: relative;
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

/* ─── 颜色选择面板 ─────────────────────────────── */
.color-picker-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.color-preset-grid {
  display: grid;
  grid-template-columns: repeat(14, 1fr);
  gap: 5px;
}

.color-preset-swatch {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 4px;
  cursor: pointer;
  border: 2px solid transparent;
  box-sizing: border-box;
  transition: transform 0.12s, border-color 0.12s;
}

.color-preset-swatch:hover {
  transform: scale(1.18);
  border-color: rgba(0,0,0,0.25);
}

.color-preset-swatch.active {
  border-color: var(--color-accent);
  transform: scale(1.1);
  box-shadow: 0 0 0 2px var(--color-accent-light);
}

.color-custom-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--color-border);
}

.color-custom-preview {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  flex-shrink: 0;
  border: 1px solid var(--color-border);
  transition: background-color 0.15s;
}

.color-custom-input {
  flex: 1;
}
</style>
