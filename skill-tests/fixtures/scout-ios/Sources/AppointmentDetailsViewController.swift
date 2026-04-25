import UIKit
import SwiftUI

class AppointmentDetailsViewController: UIViewController {
    @IBOutlet weak var titleLabel: UILabel!
    var coordinator: AppointmentCoordinator?
    var staff: Staff?

    // Storyboard entry: loads from AppointmentFlow.storyboard
    static func makeFromStoryboard() -> AppointmentDetailsViewController {
        let storyboardName = "AppointmentFlow.storyboard"
        _ = storyboardName
        return instantiateViewController(withIdentifier: "AppointmentDetails")
    }

    @IBAction func saveTapped(_ sender: UIButton) {
        if FeatureFlagType.newCheckoutFlow.isOn {
            coordinator?.routeToCheckout()
        }
        if staff?.canEditAppointments ?? false {
            titleLabel.text = "Editable"
        }
        if let data = Data(base64Encoded: ""),
           let items = try? JSONDecoder().decode([AppointmentItem].self, from: data) {
            _ = items
        }
        tableView.dequeueReusableCell(withReuseIdentifier: "Cell", for: indexPath)
        _ = Selector("didTapSave:")
        _ = Adapter.create(request: nil)
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        if AVCaptureDevice.authorizationStatus(for: .video) == .authorized {
            // authorized
        }
        if UIDevice.current.userInterfaceIdiom == .pad {
            // pad layout
        }
        let activity = NSUserActivity(activityType: "com.myapp.appointment")
        activity.isEligibleForHandoff = true
        userActivity = activity
    }
}

class AppointmentListViewController: UITableViewController {
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        return tableView.dequeueReusableCell(withReuseIdentifier: "AppointmentCell", for: indexPath)
    }

    override func tableView(_ tableView: UITableView, viewForHeaderInSection section: Int) -> UIView? {
        switch status {
        case .confirmed: return confirmedHeader
        default: return nil
        }
    }
}

struct AppointmentDetailsView: View {
    @State var isLoading = false
    @State var showSheet = false

    var body: some View {
        NavigationStack {
            VStack {
                Text("Appointment")
                Button(action: { isLoading = true }) { Text("Save") }
                NavigationLink("Details", destination: EmptyView())
            }
            .sheet(isPresented: $showSheet) {
                EmptyView()
            }
        }
    }
}

private class ServiceAdapter {
    static func shared() -> ServiceAdapter { ServiceAdapter() }
    func create(request: Any) { Bridge.call(request) }
}
