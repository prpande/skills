package com.example.appointments

import android.Manifest
import android.content.res.Configuration
import androidx.compose.foundation.clickable
import androidx.compose.runtime.Composable
import androidx.fragment.app.Fragment
import androidx.fragment.app.DialogFragment
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.SavedStateHandle
import androidx.recyclerview.widget.RecyclerView
import androidx.viewpager2.widget.ViewPager2
import io.flutter.plugin.common.MethodChannel
import retrofit2.Retrofit
import retrofit2.http.GET
import retrofit2.http.POST

// inventory_item.kind.screen
class AppointmentListFragment : Fragment() {

    private val savedStateHandle = SavedStateHandle()
    private val _uiState = MutableStateFlow<AppointmentUiState>(AppointmentUiState.Loading)
    val uiState: StateFlow<AppointmentUiState> = _uiState

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View {
        // inventory_item.source.surface.xml
        setContentView(R.layout.fragment_appointment_list)

        // inventory_item.source.surface.hybrid
        val cv = ComposeView(requireContext())
        cv.setContent {
            AppointmentListScreen()
        }
        return cv
    }

    @Composable
    fun AppointmentListScreen() {
        // inventory_item.source.surface.nav-compose
        NavHost(navController, startDestination = "appointments") {
            composable("appointments") {
                AppointmentContent()
            }
        }
        // inventory_item.kind.field
        Text("Appointments")
        Image(painter = painterResource(R.drawable.ic_calendar), contentDescription = null)
        AsyncImage(model = imageUrl, contentDescription = null)

        // inventory_item.kind.action
        Box(
            modifier = Modifier
                .clickable { onItemClick() }
        )
    }

    private fun setupViewPager() {
        // inventory_item.hotspot.type.viewpager-tab
        // Uses ViewPager2 + FragmentStateAdapter for data-driven tabs
        val viewPager = ViewPager2(requireContext())
        val pagerAdapter = AppointmentPagerAdapter(this)
        viewPager.adapter = pagerAdapter
    }

    private fun checkPermissions() {
        // inventory_item.hotspot.type.permission
        val granted = checkSelfPermission(requireContext(), android.permission.CAMERA)

        // inventory_item.hotspot.type.feature-flag
        if (FeatureFlags.isStaffSchedulingEnabled) {
            requestCameraPermission()
        }
    }

    private fun loadConfig() {
        // inventory_item.hotspot.type.config-qualifier
        val uiMode = resources.configuration.uiMode
        val nightMask = uiMode and Configuration.UI_MODE_NIGHT_MASK

        // inventory_item.hotspot.type.form-factor
        val isTablet = resources.configuration.smallestScreenWidthDp >= 600
    }

    private fun setupBottomSheet() {
        // inventory_item.hotspot.type.sheet-dialog
        val dialog = BottomSheetDialog(requireContext())
        dialog.show()
        val sheet = AppointmentSheetFragment()
        show(supportFragmentManager, "appointment_sheet")
    }

    private fun buildApi() {
        // inventory_item.hotspot.type.server-driven
        val retrofit = Retrofit.Builder()
            .baseUrl("https://api.example.com")
            .build()
        val service = retrofit.create(AppointmentService::class.java)
    }

    private fun setupFlutterBridge() {
        // code_inventory.unwalked_destinations.reason.platform-bridge
        val channel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.example/appointments",
        )
    }

    private fun loadDynamic() {
        // code_inventory.unwalked_destinations.reason.dynamic-identifier
        val cls = Class.forName("com.example.DynamicDetailFragment")
        val fragment = cls.newInstance()
    }

    private fun callAdapters() {
        // code_inventory.unwalked_destinations.reason.adapter-hosted
        val feed = FeedAdapter.create(items)
        val payment = PaymentBridge.handle(request)
    }

    inner class AppointmentViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView)

    // inventory_item.hotspot.type.view-type
    inner class AppointmentAdapter : RecyclerView.Adapter<AppointmentViewHolder>() {
        override fun getItemViewType(position: Int): Int =
            if (items[position].isPending) TYPE_PENDING else TYPE_CONFIRMED
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        // inventory_item.hotspot.type.process-death
        val key = savedStateHandle.get<String>("appointment_id")
    }
}

// inventory_item.kind.state
sealed class AppointmentUiState {
    object Loading : AppointmentUiState()
    data class Success(val appointments: List<Appointment>) : AppointmentUiState()
    data class Error(val message: String) : AppointmentUiState()
}

interface AppointmentService {
    @GET("/api/appointments")
    suspend fun getAppointments(): List<Appointment>

    @POST("/api/appointments")
    suspend fun createAppointment(appt: Appointment): Appointment
}
